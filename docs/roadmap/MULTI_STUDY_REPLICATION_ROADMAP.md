# FBF Multi-Study Research Replication Roadmap

**Status:** APPROVED — ARCHITECTURE COMPLETE
**Created:** 2026-09-02
**Scope:** ERN Parts 19, 20, 42, 49, 52 replication planning
**Authority:** Architecture approved. Implementation proceeds through the semantic gate (S0). No production code changes until S0 temporal semantics are closed and S1 is explicitly authorized.

---

## Legend

| Label | Meaning |
|-------|---------|
| **VERIFIED** | Confirmed from ERN articles or codebase inspection |
| **INFERRED** | Reasonable deduction from article evidence, but not explicitly stated; requires oracle/test verification |
| **EXISTING** | Already supported by FBF without modification |
| **GAP** | Required capability not present in FBF |
| **CANDIDATE** | Possible implementation approach (not yet decided) |
| **RECOMMENDED** | Preferred approach based on current evidence |
| **DEFERRED** | Decision postponed until more evidence is available |
| **REQUIRES MEASUREMENT** | Cannot be assessed without profiling or benchmarking |
| **REQUIRES ORACLE VERIFICATION** | Must be confirmed by running a test case against published results |
| **REQUIRES PROOF** | Must be demonstrated by implementation and comparison before the approach is adopted |
| **REQUIRES ARCHITECTURAL PROOF** | Must be demonstrated that higher-layer approaches are insufficient before engine modification is justified |
| **STATICALLY VERIFIED** | Established by code tracing and source inspection |
| **BENCHMARK-MEASURED** | Directly measured by existing benchmark infrastructure |
| **RUNTIME-MEASURED** | Established by actual execution instrumentation/profiling |

---

## A. Verified ERN Methodology

### A.1 Part 19 — Equity Glidepaths in Retirement

| Parameter | Value | Source |
|-----------|-------|--------|
| **Data period** | 1871-01 to 2015-12, monthly | Article §1 |
| **Equity returns** | S&P 500 total return (nominal) | Article §1 |
| **Bond returns** | 10-year US Treasury bonds | Article §1 |
| **Expense ratio** | 0.05% p.a. weighted | Article §1 |
| **Horizon** | 60 years | Article §1 |
| **Cohorts** | 1,700+ monthly (1871-02 to 2015-12) | Article §1 |
| **Rebalancing** | Monthly, to target weights | Article §1, Part 39 |
| **Withdrawals** | Annual, beginning of year, CPI-adjusted | Article §1 |
| **Final value targets** | 0% (depletion), 50%, 100% of real initial | Article §1 |
| **CAPE threshold** | 20 (for CAPE conditioning) | Article §1 |
| **Failure probabilities** | Fail-safe (0%), 1%, 3%, 5% percentiles | Article §1 |

**Glidepath mechanics (VERIFIED from article):**

- **Passive:** Equity weight increases by `slope` percentage points every month, regardless of market conditions.
- **Active:** Equity weight increases by `slope` percentage points only when the S&P 500 total return index (CPI-adjusted) is below its all-time high (i.e., `is_underwater`).
- **ATH definition:** The all-time high is the total return, adjusted for CPI inflation, measured at the last closing date of the month.
- **Allocation timing (article-level):** ERN describes the withdrawal occurring before the glidepath adjustment within the same month. **VERIFIED** as article-level behavior.
- **FBF temporal mapping:** Whether the existing FBF pipeline steps represent the ERN semantics exactly requires oracle verification. **REQUIRES ORACLE VERIFICATION** — this does not by itself prove that Step 20–30 → Step 40–50 matches the ERN monthly decision cycle.
- **Rebalancing:** Monthly, to the new target weights.

**Glidepath parameter grid (VERIFIED):**

| Start → End | Spread | Slopes (pp/month) |
|-------------|--------|-------------------|
| 60% → 80% | 20 pp | 0.2, 0.3 |
| 40% → 80% | 40 pp | 0.3, 0.4 |
| 20% → 80% | 60 pp | 0.4, 0.5 |
| 80% → 100% | 20 pp | 0.2, 0.3 |
| 60% → 100% | 40 pp | 0.3, 0.4 |
| 40% → 100% | 60 pp | 0.4, 0.5 |

Total: 6 start/end combos × 2 slopes × 2 modes (passive/active) = **24 glidepaths**.

Transition duration: 5.5 to 13 years depending on slope.

**Validation anchors (VERIFIED from article):**

- For 80% fixed equity: failsafe SWR = 3.14%, 1st percentile = 3.43%, 5th = 3.59%, 10th = 3.86%, 25th = 4.48%
- 60→100% glidepath with CAPE > 20: failsafe SWR = 3.47% (vs 3.25% best static) — improvement of +0.22%
- At 5% failure probability with CAPE > 20: 60→100% glidepath allows 3.57–3.63% SWR (vs 3.47% static 80%)
- 20→80% and 40→100% glidepaths are inferior to static 80% and 100% allocations

### A.2 Part 20 — More Thoughts on Equity Glidepaths

| Parameter | Value | Source |
|-----------|-------|--------|
| **Horizons** | 30 years AND 60 years | Article §2 |
| **CAPE split** | CAPE > 20 (expensive) vs CAPE ≤ 20 (cheap) | Article §2 |
| **Failure rate analysis** | SWR 3.0%–4.0% in 0.25% steps | Article §2 |

**Additional glidepaths (VERIFIED):**

| Start → End | Slopes (pp/month) | Notes |
|-------------|-------------------|-------|
| 30% → 70% | 0.111, 0.2, 0.3, 0.4 | Kitces/Pfau-inspired |
| 20% → 60% | 0.111, 0.2, 0.3, 0.4 | Low-equity variant |

Total Part 20 additions: 8 glidepaths. Grand total across Part 19+20: **32 glidepaths**.

**Validation anchors (VERIFIED from article):**

- 60→100% glidepath with CAPE > 20 at 100% FV target: failsafe = 3.34% (vs 3.05% best static) — improvement +0.29%
- 30→70% Kitces/Pfau glidepath: "consistently one of the worst performers" — worse than most static allocations
- Over 30-year horizon: best static equity is 65–75% (lower than 60-year optimum of 75–80%)
- When CAPE ≤ 20: any 90–100% static equity gives highest fail-safe SWR; glidepaths add no value

### A.3 Part 42 — One More Year Syndrome

| Parameter | Value | Classification |
|-----------|-------|---------------|
| **Initial portfolio** | $2,000,000 (linearly scalable) | VERIFIED |
| **Allocation** | 75/25 stocks/bonds throughout | VERIFIED |
| **FV target** | 25% of initial (i.e., $500,000) | VERIFIED |
| **Baseline horizon** | 30-year horizon | VERIFIED |
| **OMY duration** | 12 months | VERIFIED |
| **Contributions** | $5,000/month during OMY | VERIFIED |
| **OMY returns** | Same historical returns (no forecasting) | VERIFIED |

**Temporal semantics:**

| Element | Status | Detail |
|---------|--------|--------|
| 30-year horizon | VERIFIED | Article states "30-year horizon" |
| 360 total calendar months including OMY | INFERRED / REQUIRES VERIFICATION | Whether the 30-year horizon means 360 total months (12 OMY + 348 retirement) or 360 months of retirement after OMY is not explicitly stated; S0 must determine which interpretation ERN uses (see §K.4) |
| 12-month OMY contribution period | VERIFIED | Months 1–12: contributions, no withdrawals |
| Retirement following OMY | INFERRED | Article says "30-year horizon" with OMY; the retirement duration after OMY is not explicitly stated (see §K.4) |
| Cohort/start-date mapping | INFERRED | Article states initial portfolio is $2M at "beginning" of OMY; mapping to FBF's cohort system is inferred |
| First retirement withdrawal at month 13 | INFERRED | Article implies retirement begins after OMY; exact month index depends on period_index convention |
| period_index mapping to FBF | REQUIRES VERIFICATION | Whether FBF's 0-based period_index means period_index=12 corresponds to the 13th calendar month must be confirmed |
| Intra-month contribution/return ordering | REQUIRES VERIFICATION | Whether the $5k contribution earns that month's returns is not stated in the article |

**OMY mechanics (VERIFIED):**

- During the 12-month OMY period: zero withdrawals, $5,000/month contributions, portfolio subject to actual historical monthly returns using the 75/25 allocation.
- The initial portfolio value ($2M) is set at the **beginning** of the OMY (before contributions/returns).
- The withdrawal rate is calculated as a percentage of the **original** $2M, not the post-OMY portfolio value.
- The portfolio value at retirement (month 12) is a **random variable** depending on historical returns.

**50-year horizon variant (VERIFIED):**

- 600-month calendar horizon (VERIFIED — "50-year horizon").
- Social Security/pension: $3,000/month starting in year 31 (VERIFIED — "starting in year 31").
- FV target: 0% (capital depletion) (VERIFIED).

**Validation anchors (VERIFIED from article):**

- 30-year baseline failsafe: ~3.6% (~$72,000/year)
- OMY delay only (no contributions): +4.2% improvement
- OMY with $5,000/month contributions: +7.8% improvement
- OMY benefit is remarkably uniform: ~7.5–8% across all scenarios (30y, 50y, with/without SS)
- 50-year baseline failsafe: $67,874/year (~3.39%)
- 50-year with SS ($3k/mo from year 31): $72,031/year — nearly identical to 30-year with 25% FV target

### A.4 Part 49 — Using Leverage in Retirement

| Parameter | Value | Classification |
|-----------|-------|---------------|
| **Horizon** | 30 years (360 months) | VERIFIED |
| **Allocation** | 75/25 stocks/bonds (primary); 100/0 (comparison) | VERIFIED |
| **Initial portfolio** | $1,000,000 | VERIFIED |
| **Rebalancing** | Monthly | VERIFIED |
| **Real interest rates** | 0%, 1.5%, 3% (fixed real) | VERIFIED |
| **LTV constraint** | 75% (IB 25% margin requirement) | VERIFIED |
| **Interest treatment** | Capitalized (compounded into loan balance) | VERIFIED |
| **Loan timing** | Drawn during retirement | VERIFIED |
| **Loan repayment** | None (loan grows throughout horizon) | VERIFIED |
| **Net worth** | Portfolio Value − Loan Balance | VERIFIED |

**Conceptual leverage behavior (VERIFIED from article):**

- Leverage exists: a margin loan funds part or all of retirement spending.
- Interest is capitalized: added to loan balance, not paid out of pocket.
- Rates are fixed real (CPI-adjusted) in Part 49.
- LTV limit exists: 75% (IB 25% margin requirement).
- Repayment is absent: loan grows throughout the horizon.
- Net worth = Portfolio Value − Loan Balance.
- Forced liquidation (margin call) occurs on LTV breach.

**Monthly event ordering (INFERRED — REQUIRES ORACLE VERIFICATION):**

The article describes the leverage mechanics at a conceptual level. The exact monthly event ordering is not explicitly stated. The following must be established:

| Transition | Classification | Detail |
|-----------|---------------|--------|
| Initial draw timing | INFERRED | "drawn continuously from month 1" — but whether the first draw occurs before or after the first market evolution is not stated |
| Market evolution timing | INFERRED | Implicit in monthly simulation |
| Recurring draw timing | INFERRED | "drawn continuously" — whether the draw occurs at beginning or end of month is not stated |
| Interest accrual timing | INFERRED | "capitalized" — monthly compounding is implied but exact timing relative to draws is not stated |
| Withdrawal timing | INFERRED relative to loan mechanics | Standard retirement withdrawal, but ordering relative to loan draw is not stated |
| LTV evaluation point | INFERRED | "at all times" — whether evaluated after every state transition or only at month-end is not stated |
| Margin-call detection | INFERRED | Whether detected at moment of violation or at evaluation point is not stated |

**Partial leverage model (VERIFIED):**

- Total spending rate: 4% of initial portfolio ($40,000/year on $1M)
- Portfolio withdrawal rate: 3% ($30,000/year = $2,500/month)
- Margin loan draw rate: 1% ($10,000/year = $833.33/month)
- This is the recommended starting point per the article.

**Validation anchors (VERIFIED from article):**

- 1929 cohort, full leverage, 100% equity: depleted after 12 years
- 1929 cohort, 75/25, full leverage: near wipeout at month 238 ($1.085M loan vs $1.185M portfolio)
- 1965 cohort, 30y, 4% WR, partial leverage ($30k portfolio + $10k loan): LTV stayed below 70% even at worst point
- 1965 cohort, 30y, 4% WR, 50% leverage ($20k portfolio + $20k loan): LTV reached 84–93% depending on rate — likely margin call

### A.5 Part 52 — Timing Leverage in Retirement

| Parameter | Value | Classification |
|-----------|-------|---------------|
| **Horizon** | 30 years (360 months) | VERIFIED |
| **Allocation** | 75/25 stocks/bonds | VERIFIED |
| **Drawdown trigger** | 20%+ below real S&P 500 TR ATH | VERIFIED |
| **Thresholds tested** | 20%, 25%, 30%, 35% | VERIFIED |
| **FFR+spread scenarios** | 0.50%, 1.25%, 2.75% | VERIFIED |
| **LTV constraint** | 50% (2x leverage max) | VERIFIED |
| **Repayment trigger** | Fresh ATH in real S&P 500 TR | VERIFIED |
| **Repayment mechanism** | Double withdrawal from portfolio, excess pays loan | VERIFIED |
| **Final net worth target** | $250,000 (real) | VERIFIED |
| **Solver objective** | Maximize WR | VERIFIED |
| **Solver variables** | WR + Borrow% | VERIFIED |

**Conceptual timing behavior (VERIFIED from article):**

- Leverage activates below the specified drawdown threshold.
- Borrow% controls the share funded by the loan.
- Repayment occurs at a fresh ATH.
- Repayment uses additional portfolio withdrawal (double the budget).
- FFR + spread determines the floating rate.
- LTV constraint exists at 50%.

**Monthly event ordering (INFERRED — REQUIRES ORACLE VERIFICATION):**

The exact FBF monthly event ordering is not explicitly stated in the article. The following must be established:

| Transition | Classification | Detail |
|-----------|---------------|--------|
| Market returns applied | INFERRED | "simulated monthly" but whether this is first or last step is not stated |
| Drawdown evaluation | INFERRED | "I check if the S&P 500 TR index is 20+% below" — timing relative to market returns is not stated |
| Loan draw / portfolio withdrawal | INFERRED | Monthly decision based on drawdown evaluation |
| Repayment | INFERRED | "if we reach a fresh all-time high... we'll start paying back" — same month or next month is not stated |
| Interest accrual | INFERRED | Monthly compounding implied but timing relative to other steps is not stated |
| LTV constraint evaluation | INFERRED | "50% upper limit" — evaluation point in monthly cycle is not stated |

**Decided temporal semantics (DECIDED — S0-F5, S0-F6):**

1. Drawdown evaluation uses beginning-of-period market state.
2. Repayment occurs in the same month as fresh ATH detection.
3. Interest accrual is applied at end of period.
4. LTV constraint is evaluated continuously (debt is subject to margin-call conditions from the moment it is borrowed).

These decisions are **shared with Part 49** and are consistent across both studies.

**Validation anchors (VERIFIED from article):**

- 1965 cohort, no leverage baseline: WR = 3.58%
- 1965 cohort, no timing, FFR+0.50%: WR = 3.78%, Borrow% = 10.76%
- 1965 cohort, 20% threshold + repayment: WR = 3.91%, Borrow% = 41.08% — improvement of ~33–36bps (~9–10%)
- 1965 cohort, 25% threshold, FFR+0.50%: WR = 3.92%
- 1965 cohort, 25% threshold, FFR+1.25%: WR = 3.87%
- 1965 cohort, 25% threshold, FFR+2.75%: WR = 3.75%
- 1929 cohort, no timing: WR = 4.39% — leverage already very effective without timing
- 1929 cohort, 35% threshold + repayment: WR = 4.93% — best result

---

## B. Existing FBF Architecture Baseline

### B.1 Repository Identity

| Property | Value |
|----------|-------|
| Package name | `fbf-core` |
| Root namespace | `fbf.core` |
| Third-party runtime deps | **Zero** |
| Python requirement | ≥ 3.13 |
| Current version | 0.1.0 |

### B.2 Layer Architecture

```
Tier 1: fbf.core (root facade)           → All consumers
Tier 2: fbf.core.domain, study,          → Consumers with explicit need
        execution, optimization,
        persistence
Tier 3: All internal submodules           → Core tests only
```

### B.3 Simulation Pipeline (9-Step Monthly Loop)

| Order | Step | Purpose |
|-------|------|---------|
| 0 | InitializeAllocationStep | Seeds initial allocation for month-0 |
| 10 | BuildDecisionContextStep | Constructs immutable DecisionContext |
| 20 | WithdrawalDecisionStep | Calls withdrawal_policy.decide(context) |
| 30 | WithdrawalExecutionStep | Executes withdrawal via service |
| 40 | AllocationDecisionStep | Calls allocation_policy.decide(context) |
| 50 | PortfolioRebalanceStep | Executes rebalance via service |
| 60 | MarketEvolutionStep | Applies market evolution via service |
| 70 | MonthlyResultBuilderStep | Captures state into MonthlyResult |
| 80 | SimulationStateUpdateStep | Advances to next month |

### B.4 Current Policy Model

**Policies are stateless.** They receive all state via the immutable `DecisionContext`:

```python
@dataclass(frozen=True)
class DecisionContext:
    date: date
    period_index: int
    simulation_context: object
    portfolio: Portfolio
    current_allocation: Allocation
    target_allocation: AllocationTarget
    market_snapshot: MarketSnapshot
    dataset: Dataset
```

**Existing policies (EXISTING):**
- `ConstantAllocationPolicy` — fixed equity/bond split
- `ConstantWithdrawalPolicy` — fixed-rate (portfolio-based)
- `FixedRealWithdrawalPolicy` — fixed real amount (computed once at start)

**Policy lifecycle:** `before_simulation → before_month → decide → PolicyDecision → after_month → after_simulation`

### B.5 Current MarketSnapshot

```python
@dataclass(frozen=True)
class MarketSnapshot:
    date: date
    index_levels: dict[AssetClass, Decimal]
    inflation: Decimal
    inflation_cumulative: Decimal
    is_ath: bool          # ← EXISTS
    is_underwater: bool   # ← EXISTS
    running_ath: Decimal
    cape: Decimal | None = None  # ← EXISTS
```

### B.6 Current SimulationState (Execution Layer)

```python
@dataclass
class SimulationState:
    context: SimulationContext
    current_date: date
    period_index: int
    portfolio: Portfolio
    allocation: Allocation | None
    allocation_target: AllocationTarget | None
    allocation_drift: object | None
    withdrawal_decision: WithdrawalDecision | None
    allocation_decision: AllocationDecision | None
    current_withdrawal: Money | None
    market_snapshot: MarketSnapshot | None
    current_wealth: Money | None
    peak_wealth: Money | None
    failure_state: str | None
    status: ExecutionStatus | None
    decision_context: DecisionContext | None
    monthly_results: list[MonthlyResult]
```

**Note:** No debt/liability fields. No pre-retirement phase. No leverage state. (EXISTING)

### B.7 Current Execution Capabilities

- **Reference Decimal engine** — bit-exact, canonical (EXISTING)
- **Decimal Fast Path** — closed-form for ConstantAllocation + FixedRealWithdrawal (EXISTING)
- **Numba Float64 Fast Path** — approximate, opt-in (EXISTING)
- **Multi-horizon execution** — prefix-consistent derivation (EXISTING)
- **Parallel execution** — deterministic, process-based (EXISTING)
- **Trajectory deduplication** — identical contexts share execution (EXISTING)

### B.8 Current Research Layer

- **Part 3 Planner** — CAPE-aware cohort manifest, regime aggregation (EXISTING)
- **`materialize_research_plan()`** — builds ResearchPlan from experiment definition (EXISTING)
- **Part 3 Aggregation** — groups results by CAPE regime (EXISTING)
- **Part 3 Pipeline** — adapt → execute → aggregate (EXISTING)

### B.9 Current Result Model

```python
@dataclass(frozen=True)
class SimulationStatistics:
    final_wealth: Money
    max_drawdown: float
    success: bool
    failure_month: int | None
    months_simulated: int
    execution_time_seconds: float

@dataclass(frozen=True)
class MonthlyResult:
    date: date
    period_index: int
    market_snapshot: MarketSnapshot
    portfolio: Portfolio
    allocation: Allocation | None
    allocation_target: AllocationTarget | None
    allocation_drift: object | None
    withdrawal_decision: WithdrawalDecision | None
    rebalance_result: object | None
    drawdown: float
    cumulative_return: float
    cumulative_inflation: float
    events: Sequence[object]
```

**MonthlyResult already contains full per-month traces.** (EXISTING)

### B.10 Current Data Assets

| Dataset | On-disk size | Snapshots | Deep memory | Range |
|---------|-------------|-----------|-------------|-------|
| `ern_swr_h720.json` | 558 KB | 2,459 | ~2.2 MB | 1871-01 to 2075-11 |
| `ern_cape_1871_2016.json` | 462 KB | 1,571 | ~1.6 MB | 1881-01 to 2023-09 |

---

## C. Architectural Gap Analysis

### C.1 Dynamic Allocation Policy (Glidepath)

**VERIFIED requirement:** Parts 19/20 require allocation that changes monthly based on a schedule (passive) or market conditions (active). The slope is in **percentage points per month**.

**EXISTING capability:** `ConstantAllocationPolicy` is fixed. `DecisionContext` provides `market_snapshot.is_ath` and `market_snapshot.is_underwater`. Policy lifecycle is stateless.

**GAP:** No mechanism for allocation that changes over time. No glidepath state tracking.

**CANDIDATE approaches:**

1. **Period-indexed (RECOMMENDED):** `equity_weight = f(period_index, start, end, slope)`. Policy remains stateless; allocation is deterministic from `period_index`.
2. **Stateful policy (CANDIDATE):** Policy tracks current equity weight internally, advances each month.

**RECOMMENDED:** Period-indexed. Preserves policy statelessness.

**DEFERRED:** Whether period-indexed suffices for all glidepath variants. Must verify timing semantics: does the allocation change happen before or after market evolution in the same month? **This mapping requires oracle verification.**

### C.2 Pre-Retirement Accumulation Phase (Part 42)

**VERIFIED requirement:** 12 months of contributions ($5,000/month) before retirement begins. Historical returns apply during OMY. No withdrawals during OMY. Same cohort universe as baseline. FV target is 25% of initial. See §A.3 for complete temporal semantics.

**EXISTING capability:** Simulation starts withdrawal at month-0. No contribution mechanism.

**GAP:** No mechanism for pre-retirement accumulation or contributions.

**CANDIDATE approaches:**

1. **Research-layer pre-processing (CANDIDATE):** Run a 12-month "accumulation simulation" with zero withdrawals and positive contributions, using historical returns. Use the resulting portfolio value as the starting point for the retirement simulation.

2. **Engine-level contribution step (CANDIDATE):** Add a `ContributionStep` to the pipeline. Add `monthly_contribution: Money | None` to `SimulationContext`. The simulation runs for 360 months total: months 1–12 have contributions and zero withdrawals, months 13–360 have normal withdrawals.

**Semantic specification (before implementation):**

Before either approach is implemented, establish whether the research-layer and engine-level formulations are mathematically expected to represent the same process. This specification must cover:

- State transition definition: what changes each month under each formulation.
- Contribution timing: when the $5k is added relative to market returns.
- Return timing: which month's return applies to which month's balance.
- Period mapping: how calendar months map to simulation periods under each formulation.
- Starting portfolio semantics: what "$2M initial" means under each formulation.
- Withdrawal activation: when the first withdrawal occurs under each formulation.
- Historical trajectory alignment: whether the same historical return sequence is applied to the same calendar months under each formulation.

**This semantic specification is an S0 prerequisite for P42.** It establishes whether the two formulations are *expected* to be equivalent, based on their mathematical structure.

**Implementation equivalence gate (after implementation):**

If both formulations are actually implemented, independently compare their numerical results. This is an **implementation-phase acceptance criterion**, not a prerequisite for starting P42.

**RECOMMENDED:** Investigate both approaches. Research-layer first (simpler). Establish the semantic specification before implementation; verify numerical equivalence after.

**Engine change assessment (if engine-level approach is chosen):**
- Can the requirement be expressed above the engine? **CANDIDATE** — research-layer approach exists but is unproven sufficient.
- If engine change is needed: add `ContributionStep` (sequence_order between 20 and 30?), extend `SimulationContext` with `monthly_contribution`.
- Existing behavior unchanged: contributions default to zero.
- Decimal reference engine remains oracle: contributions are simple additions, no arithmetic complexity.

### C.3 Debt/Liability State (Margin Loan)

**VERIFIED requirement:** Parts 49/52 require tracking a margin loan balance, accruing interest (capitalized), and enforcing LTV constraints. Part 49: LTV ≤ 75%, fixed real rate, no repayment. Part 52: LTV ≤ 50%, FFR+spread, repayment at ATH.

**S0 must establish two distinct things:**

**A. Debt semantic model** — What happens to:
- loan balance
- interest
- draws
- repayments
- portfolio value
- LTV
- forced liquidation
- net worth

**B. Architectural representation** — Where those concepts live:
- research layer
- policy layer
- execution state
- domain model
- engine

The semantic model (A) must be established before deciding where the state belongs (B). The architectural representation decision remains DEFERRED until the semantic model is fully specified.

**VERIFIED from articles:**

- Leverage exists: a margin loan funds part or all of retirement spending.
- Interest is capitalized: added to loan balance, not paid out of pocket.
- Rates are fixed real (CPI-adjusted) in Part 49; FFR+spread in Part 52.
- LTV limit exists: 75% in Part 49, 50% in Part 52.
- Repayment is absent in Part 49; present at fresh ATH in Part 52.
- Net worth = Portfolio Value − Loan Balance.
- Forced liquidation (margin call) occurs on LTV breach.

**INFERRED / REQUIRES ORACLE VERIFICATION:**

- Exact initial draw timing relative to first market evolution.
- Exact monthly draw timing (beginning vs end of month).
- Exact interest accrual point (before/after draws, before/after market evolution).
- Exact ordering between draw and interest within a month.
- Exact LTV evaluation point in the monthly cycle.
- Exact margin-call transition (moment of violation vs end-of-month check).

**What must be modeled — required debt state transitions:**

Part 49:
- Month 1: loan balance = initial draw amount
- Each subsequent month: balance += interest; balance += new draw
- Constraint: `balance / portfolio_value <= 0.75` at all times
- No repayment

Part 52 adds:
- Trigger evaluation: `is_underwater` and drawdown magnitude
- Conditional draws: if trigger active, draw loan for `Borrow%` of budget
- Repayment: if fresh ATH and loan exists, double withdrawal, excess pays loan
- Interest still accrues monthly on outstanding balance
- Constraint tightened to `balance / portfolio_value <= 0.50`

**Architectural representation decision (DEFERRED — REQUIRES ARCHITECTURAL PROOF):**

The roadmap defines the required behavior first. The concrete architectural representation is decided after the transitions and temporal ordering are fully understood. The choice must be driven by:

1. **Temporal ordering** — when each state transition occurs relative to market evolution, withdrawals, and other steps.
2. **LTV constraint evaluation** — at which point in the monthly cycle the constraint is checked.
3. **State lifetime** — whether the debt state persists across months (requiring mutable state or cross-month propagation) or is recomputable from inputs.
4. **Policy access requirements** — whether policies need to observe the debt balance in `DecisionContext`.
5. **Domain purity** — the domain layer must not import from execution.
6. **Engine interface sufficiency** — whether the existing policy/pipeline interfaces can express the full debt lifecycle without engine modification.

Options: policy/research layer, execution state, domain concept, engine extension (if proven necessary).

**Engine change assessment (REQUIRES ARCHITECTURAL PROOF):**

Engine modification is only justified if the required state transitions cannot be represented cleanly above the engine. The proof requires:

1. Specifying what state is required (loan balance, interest rate, LTV ratio, trigger state).
2. Specifying when each piece of state is produced (which step, relative to which other steps).
3. Identifying which existing interfaces can observe the state (`DecisionContext`, policy `decide()` method, pipeline steps).
4. Attempting to express the full lifecycle using only policy/research/execution-layer mechanisms.
5. Identifying specifically which requirement fails under the higher-layer model.
6. Only then concluding whether an engine change is justified.

### C.4 Drawdown-Triggered Leverage (Part 52)

**VERIFIED from article:** Leverage activates below the specified drawdown threshold. Borrow% controls the share funded by the loan.

**INFERRED / REQUIRES ORACLE VERIFICATION:** Whether drawdown is evaluated before or after the monthly market return. Exact trigger timing relative to other monthly events.

**GAP:** No market-state-dependent policy switching. No drawdown magnitude calculation relative to ATH.

**CANDIDATE approach:** New withdrawal policy that selects between portfolio withdrawal and margin loan draw based on `is_underwater` and drawdown percentage. Requires debt state (C.3).

### C.5 Loan Repayment Logic (Part 52)

**VERIFIED from article:** Repayment occurs at a fresh ATH. Repayment uses additional portfolio withdrawal (double the budget).

**INFERRED / REQUIRES ORACLE VERIFICATION:** Whether repayment occurs in the same month as ATH detection. Exact ordering relative to interest accrual and normal withdrawals.

**GAP:** No debt repayment mechanism.

**CANDIDATE approach:** Extend the leverage withdrawal policy (C.4) with repayment logic.

### C.6 Floating-Rate Interest (Part 52)

**VERIFIED requirement:** FFR + spread (0.50%, 1.25%, 2.75%). Interest rate varies over time with FFR.

**GAP:** No FFR dataset. No mechanism for date-dependent interest rates.

**Investigation required (DEFERRED — REQUIRES MEASUREMENT):**

1. **Exact source:** What dataset does ERN use for FFR?
2. **Historical coverage:** Does the FFR series cover 1871–2015?
3. **Frequency:** Monthly?
4. **Definition:** Effective FFR, target rate, or proxy?
5. **Monthly transformation:** How converted to monthly rate?
6. **Date alignment:** When does a rate change take effect?
7. **Treatment of rate changes:** Mid-month handling?
8. **Correspondence with ERN calculation:** Same transformation?

### C.7 Solver/Optimization (Part 52)

**VERIFIED requirement:** Excel Solver maximizes WR subject to: $250K final net worth + 50% LTV constraint. Decision variables: WR + Borrow%.

**CANDIDATE approaches:**

1. FBF optimization layer (if it supports this constraint type)
2. External solver (violates zero-dep rule)
3. Manual parameter sweep

**Manual parameter sweep — sufficiency analysis (DEFERRED — REQUIRES MEASUREMENT):**

1. WR resolution needed for reported precision.
2. Borrow% resolution needed for reported precision.
3. Constraint handling for every grid point.
4. Sensitivity to $250K constraint precision.
5. Sensitivity to LTV evaluation point.
6. Grid refinement requirements.
7. Convergence toward optimum.

---

## D. Temporal Semantics Gate

### D.1 Purpose

This gate establishes the exact monthly event ordering for each study before any implementation begins.

### D.2 Current FBF Pipeline Order (EXISTING)

```
10: BuildDecisionContext
20: WithdrawalDecision
30: WithdrawalExecution      ← portfolio value decreases
40: AllocationDecision
50: PortfolioRebalance        ← holdings adjusted to target
60: MarketEvolution           ← returns applied to holdings
70: MonthlyResultBuilder
80: SimulationStateUpdate
```

### D.3 Per-Study Temporal Semantics Audit

#### Part 19/20 — Glidepaths

| Transition | Article evidence | FBF structural mapping | ERN temporal equivalence | Classification |
|-----------|---------------------|---------------------|------------------------|----------------|
| Withdrawal occurs | "withdrawal taken out" | Step 20–30 | DECIDED (S0-F1) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |
| Allocation change | "then glidepath adjustment made" | Step 40–50 | DECIDED (S0-F1) | FBF mapping: INFERRED; ERN equivalence: DECIDED |
| Market returns applied | Implicit in monthly simulation | Step 60 | DECIDED (S0-F1) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |
| Rebalancing to new target | "monthly rebalancing" | Step 50 | DECIDED (S0-F1) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |

#### Part 42 — OMY

| Transition | Article evidence | FBF structural mapping | ERN temporal equivalence | Classification |
|-----------|---------------------|---------------------|------------------------|----------------|
| Contribution added | "entered as positive supplemental cash flows" | **NO EXISTING STEP** | DECIDED (S0-F3) | GAP; ERN equivalence: DECIDED |
| Market returns during OMY | "same historical returns" | Step 60 (if extended) | DECIDED (S0-F3) | FBF mapping: INFERRED; ERN equivalence: DECIDED |
| No withdrawals during OMY | "scaling of withdrawals set to zero" | Step 20–30 (withdrawal = 0) | DECIDED (S0-F4) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |
| First retirement withdrawal | Article implies post-OMY | Step 20–30 at appropriate period_index | DECIDED (S0-F4) | FBF mapping: INFERRED; ERN equivalence: DECIDED |

#### Part 49 — Leverage (Untimed)

| Transition | Article evidence | FBF structural mapping | ERN temporal equivalence | Classification |
|-----------|---------------------|---------------------|------------------------|----------------|
| Loan draw | "drawn continuously from month 1" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| Interest accrual | "capitalized" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| LTV constraint evaluation | "at all times" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| Market returns applied | Implicit | Step 60 | DECIDED (S0-F5) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |
| Portfolio withdrawal | Standard retirement withdrawal | Step 20–30 | DECIDED (S0-F5) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |
| Rebalancing | Monthly | Step 50 | REQUIRES IMPLEMENTATION VALIDATION | FBF mapping: VERIFIED; Chosen semantic contract: DECIDED where explicitly decided; ERN equivalence: REQUIRES IMPLEMENTATION VALIDATION |

#### Part 52 — Timing Leverage

| Transition | Article evidence | FBF structural mapping | ERN temporal equivalence | Classification |
|-----------|---------------------|---------------------|------------------------|----------------|
| Market returns applied | "simulated monthly" | Step 60 | DECIDED (S0-F5) | FBF mapping: INFERRED; ERN equivalence: DECIDED |
| Drawdown evaluation | "I check if the S&P 500 TR index is 20+% below" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| Loan draw (conditional) | "borrow% of budget comes from margin loan" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| Portfolio withdrawal | Standard retirement withdrawal | Step 20–30 | DECIDED (S0-F5) | FBF mapping: VERIFIED; ERN equivalence: DECIDED |
| Repayment (conditional) | "double the withdrawals... excess pays down loan" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| Interest accrual | Implied monthly compounding | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |
| LTV constraint evaluation | "50% upper limit" | **NO EXISTING STEP** | DECIDED (S0-F5) | GAP; ERN equivalence: DECIDED |

### D.4 Gate Completion Criteria

**Classification rule:** Every item classified as a prerequisite for a study must be **CLOSED** before that study starts. Items that are genuinely non-blocking may remain **DEFERRED**, but must be explicitly classified as non-blocking and must not be required for the affected phase. A prerequisite cannot be closed by deferring it.

---

## E. IO / Serialization / ProcessPool Audit

### E.1 Audit Methodology

This audit was performed by:
1. Code tracing the construction path from YAML → ResearchPlan → ProcessPoolExecutor initargs.
2. Measuring actual pickle sizes by constructing plans at different cardinalities and serializing them.
3. Estimating deserialized worker memory using tracemalloc on unpickled initargs.

No instrumentation was added to production code. All measurements were performed in `/tmp/` scripts.

Evidence is classified as:
- **STATICALLY VERIFIED** — established by code tracing and source inspection.
- **BENCHMARK-MEASURED** — directly measured by existing benchmarks (`tests/benchmarks/`).
- **PICKLE-MEASURED** — measured by temporary pickle topology scripts (this audit).
- **STATIC ESTIMATE** — derived from source structure and measured components.

### E.2 Full ERN Plan Cardinality

**Source files traced:**
- `tests/oracle/ern/constants.py:99-108` — grid dimensions
- `src/fbf/core/study/plan.py:159-237` — `materialize_research_plan()`
- `src/fbf/core/study/builder.py:435-487` — `build_study_plan()`
- `src/fbf/core/execution/strategies/parallel_executor.py:540-543` — initargs construction
- `src/fbf/core/execution/strategies/reference.py:414-506` — `execute_reference()`

**Full ERN grid (STATICALLY VERIFIED):**

| Dimension | Value | Source |
|-----------|-------|--------|
| Dataset snapshots | 2,459 | `ern_swr_h720.json` |
| Longest horizon | 721 months (60y + 1 pre-retirement) | `builder.py:448` |
| Cohorts (per longest horizon) | **1,739** | `2459 - 721 + 1` via `CohortGenerator` |
| Equity allocations | 5 | `[1.0, 0.75, 0.5, 0.25, 0.0]` |
| Withdrawal rates | 9 | `[0.03 .. 0.05]` |
| Horizons | 4 | `[30, 40, 50, 60]` years |
| Parameter configurations | **180** | 5 × 9 × 4 |
| Full grid cells | **180** | Same as param configs |
| **Full grid units** | **313,020** | 180 × 1,739 |

**The 180-cell grid means 180 parameter configurations per cohort.** The full ERN execution produces 313,020 PlannedSimulationUnit objects.

### E.3 Construction Path to initargs

**Source traced (STATICALLY VERIFIED):**

`materialize_research_plan()` iterates `1,739 cohorts × 180 param_configs = 313,020` iterations, producing one `PlannedSimulationUnit` per iteration. The `ResearchPlan` stores `units=tuple(units)` — all 313,020 units in a single tuple.

`parallel_execute()` (line 540-543) passes the **full** `plan.units` and `plan.experiment_definition` as `initargs` to `ProcessPoolExecutor`:

```python
with executor_cls(
    max_workers=effective_workers,
    initializer=_initialize_worker,
    initargs=(plan.experiment_definition, plan.units, simulation_executor),
) as executor:
```

`_initialize_worker()` (line 248-262) stores these as module-level globals. **Every worker receives the complete plan.** There is no partitioning before worker initialization.

**The reference executor** (`execute_reference()`, line 414-506) slices by 100 cohorts before calling `parallel_execute()`:

```python
slices = _slice_plan_units(plan, slice_cohorts=100)
for slice_units in slices:
    sub_plan = ResearchPlan(experiment_definition=plan.experiment_definition, units=slice_units)
    sub_result = parallel_execute(sub_plan, ...)
```

Each slice contains `100 cohorts × 180 configs = 18,000 units`. Workers within each slice receive the 18,000-unit sub-plan. Slices are processed sequentially.

### E.4 Pickle Topology (PICKLE-MEASURED)

**Measurement method:** Temporary script in `/tmp/measure_pickle.py`. Plan constructed via `materialize_research_plan()` using `ern_swr_h720` dataset. Pickle sizes measured with `pickle.dumps()`.

| Case | Units | `pickle(exp_def)` | `pickle(units)` | `pickle(initargs)` | Unique Datasets | Unique Snapshots | Memo% |
|------|------:|---------:|---------:|---------:|--------:|---------:|------:|
| A: 1 cohort × 180 | 180 | 458 KiB | 156 KiB | 491 KiB | 4 | 721 | 99.1% |
| B: 10 cohorts × 180 | 1,800 | 458 KiB | 335 KiB | 679 KiB | 40 | 730 | 99.8% |
| C: 100 cohorts × 180 | 18,000 | 462 KiB | 2.08 MiB | 2.51 MiB | 400 | 820 | 99.9% |
| **D: Full ERN** | **313,020** | **522 KiB** | **33.94 MiB** | **36.05 MiB** | **6,956** | **2,459** | **99.9%** |

**Key finding: pickle memoization deduplicates 99.9% of repeated Dataset/MarketSnapshot objects.** The naive sum of 313,020 individually pickled units would be ~29.7 GiB. Actual pickle: 33.94 MiB.

**Object topology (PICKLE-MEASURED):** 313,020 units reference only 6,956 unique Dataset objects (4 per cohort × 1,739 cohorts). Each Dataset wraps a tuple of MarketSnapshot objects from the canonical trajectory. The 2,459 unique MarketSnapshot objects are shared across all Dataset slices.

**Initargs = `pickle((exp_def, units, None))`:** ~36.05 MiB for the full plan. The `exp_def` pickle (~522 KiB) is mostly already memoized within the `units` pickle, adding only ~2 MiB.

### E.5 Reference Executor Slice Sizes

The reference executor slices by 100 cohorts before calling `parallel_execute()`. Within each slice:

| Slice | Units | `pickle(initargs)` |
|-------|------:|---------:|
| 100 cohorts × 180 configs | 18,000 | **2.51 MiB** |

The full ERN grid (1,739 cohorts) produces ~18 sequential slices. Each `parallel_execute()` call receives a 2.51 MiB initargs payload.

### E.6 Deserialized Worker Memory (PICKLE-MEASURED + STATIC ESTIMATE)

**Measurement method:** Temporary script in `/tmp/measure_memory.py`. Initargs pickled, then unpickled in the same process. Deserialized graph measured via `tracemalloc`.

**Per-worker deserialized memory (PICKLE-MEASURED):**

| Case | Units | Deserialized graph | Peak during unpickle |
|------|------:|---------:|---------:|
| D: Full ERN | 313,020 | **110.38 MiB** | 198.74 MiB |
| C: 100-cohort slice | 18,000 | **~6.3 MiB** (extrapolated) | ~11.4 MiB (extrapolated) |

**Object identity after unpickling (PICKLE-MEASURED):** Unpickled objects do NOT share identity with originals. Each worker gets an independent Python object graph.

**Unique object counts in deserialized graph (PICKLE-MEASURED):**
- 6,956 unique Dataset objects (full plan) or 400 (100-cohort slice)
- 2,459 unique MarketSnapshot objects (full trajectory, shared across Dataset slices within each worker)

**Within-worker Dataset sharing (STATICALLY VERIFIED):** Within a single worker process, multiple `PlannedSimulationUnit` objects may reference the same `Dataset` instance when plan materialization reuses that object. Two units referencing the same `(start_date, horizon_months)` share the same Dataset instance — no copy. The dominant memory cost is the 6,956 Dataset wrapper objects (each holding a tuple of MarketSnapshot references), not the MarketSnapshot data itself.

### E.7 Fork/COW Semantics (STATICALLY VERIFIED + PICKLE-MEASURED)

**ProcessPool start method (STATICALLY VERIFIED):**

No `mp_context` parameter is passed to `ProcessPoolExecutor`. The start method is therefore platform- and Python-version-dependent. The relevant runtime start method can be checked with `multiprocessing.get_start_method()`. This audit must not assume `fork` unless the runtime actually uses it.

**What happens when fork is used (STATICALLY VERIFIED):**

1. **Fork time:** Child inherits parent's address space via copy-on-write (COW). Pages are shared until modified.

2. **initargs serialization:** `ProcessPoolExecutor` serializes `(exp_def, units, None)` through a pipe. This is a separate copy of the data, independent of the fork-inherited address space. Serialized size: ~36 MiB (full plan) or ~2.5 MiB (100-cohort slice).

3. **Worker deserialization:** `_initialize_worker` unpickles the initargs, creating ~110 MiB of new Python objects (full plan) or ~6.3 MiB (100-cohort slice).

4. **Global replacement:** `_initialize_worker` overwrites module-level globals:
   ```python
   _WORKER_EXPERIMENT_DEFINITION = exp_def
   _WORKER_UNITS = tuple(units)
   ```
   This replaces references to the fork-inherited objects with references to the newly deserialized objects.

**Cross-process identity (PICKLE-MEASURED):**

Workers receive independently deserialized Python object graphs, so Python object identity is not shared across processes. The behavior of OS-level COW pages (RSS/PSS) was not measured and is not claimed.

**Quantified duplication (PICKLE-MEASURED + STATIC ESTIMATE):**

| Component | Parent | Per worker | 8 workers |
|-----------|--------|-----------|-----------|
| Dataset + MarketSnapshot objects | ~34 MiB | ~110 MiB (deserialized) | ~880 MiB |
| Total | ~34 MiB | ~110 MiB | ~914 MiB |

**However:** The reference executor slices by 100 cohorts, so each `parallel_execute()` call receives only 18,000 units:

| Component | Parent | Per worker | 8 workers |
|-----------|--------|-----------|-----------|
| Dataset + MarketSnapshot objects | ~3 MiB | ~6.3 MiB | ~50 MiB |
| Total | ~3 MiB | ~6.3 MiB | ~53 MiB |

### E.8 Within-Process vs Cross-Process Sharing

**Within-process sharing (STATICALLY VERIFIED):**

Within a single process (parent or worker), `Dataset` objects are shared by Python identity when plan materialization reuses that object. Two `PlannedSimulationUnit` objects pointing to the same `Dataset` instance share the same in-memory `Dataset` — no copy. The parent plan (313,020 units) shares only 6,956 unique Dataset objects.

**Cross-process sharing (STATICALLY VERIFIED):**

Each worker deserializes its own copies through `_initialize_worker`. After deserialization, each worker has its own independent Python object graph. **Python object identity cannot establish cross-process sharing.** The behavior of OS-level COW pages (RSS/PSS) was not measured and is not claimed.

**The distinction matters:** Within-process, 313,020 units share 6,956 Datasets (memory = ~34 MiB). Across 8 processes, each holds ~110 MiB independently (total = ~914 MiB). The duplication factor is ~27× for the full plan.

### E.9 Per-Task and Per-Return Costs

**Per-task serialization (STATICALLY VERIFIED):** Only `tuple[int, ...]` (unit indices) + `bool` (summary_only). Approximately a few hundred bytes per task.

**Per-return serialization (BENCHMARK-MEASURED):** `SimulationResult` pickle is ~171 KB (full timeline, 720 months) or ~2 KB (summary-only mode). Summary-only reduces return-path serialization by ~99%.

**Note:** Existing benchmarks use `ThreadPoolExecutor` (`use_processes=False`). They do not measure actual cross-process pickle behavior. The pickle sizes are accurate for the serialization step but do not reflect fork-based COW behavior.

### E.10 Optimization Categories

**A. Mathematical work (STATICALLY VERIFIED):**

- Monthly simulation recurrence, policy decisions, horizon chaining.
- Fast path: closed-form for ConstantAllocation + FixedRealWithdrawal (already implemented).
- Multi-horizon derivation: shorter horizons derived from longest evaluation (already implemented).
- For glidepath policies (not eligible for fast path): each month requires one policy decision + one market evolution step.

**B. Execution overhead (STATICALLY VERIFIED):**

- Process-based parallelism: already implemented.
- Worker initialization: large objects seeded once per worker via `initargs`.
- Task dispatch: integer indices only.
- Summary-only mode: timelines stripped before cross-process transfer (BENCHMARK-MEASURED: ~171 KB → ~2 KB per result).

**C. IO (STATICALLY VERIFIED):**

- Dataset loading/materialization: source datasets are loaded/materialized once before execution. Worker processes receive the materialized objects through ProcessPool initialization and do not reopen source files during simulation.
- Dataset slicing: once per unique (cohort, horizon) pair with identity sharing.
- No runtime network access, no database reads during simulation.

**D. Serialization / IPC (PICKLE-MEASURED):**

- Per-worker init: ~2.5 MiB (100-cohort slice) or ~36 MiB (full plan). Amortized across all tasks.
- Per-task: ~few hundred bytes (integer indices).
- Per-return: ~2 KB (summary-only).
- Pickle memoization reduces unit serialization by 99.9%.

**E. Memory amplification (PICKLE-MEASURED + STATIC ESTIMATE):**

- Cross-process Dataset duplication exists: each worker deserializes independent copies.
- Full plan: ~110 MiB per worker, ~914 MiB across 8 workers.
- 100-cohort slice (reference executor): ~6.3 MiB per worker, ~53 MiB across 8 workers.
- Fork COW provides transient address-space sharing, but `_initialize_worker` subsequently creates an independent deserialized object graph. Therefore, the architecture cannot rely on COW as its data-sharing mechanism. OS-level RSS/PSS effects were not measured.

### E.11 Batching Assessment

**Question A: Is it architecturally necessary for every worker to receive the complete PlannedSimulationUnit collection?**

No. Workers only process integer index batches. They could receive a smaller representation.

**Question B: Could workers receive cohort/configuration identifiers + shared dataset representation?**

Yes. Workers could receive:
- Cohort specification (start_date, cohort_index)
- Parameter configuration (equity_allocation, withdrawal_rate, horizon_years)
- A reference to a preloaded Dataset (via process-local cache)

This would reduce initargs from ~2.5 MiB (100-cohort slice) to ~few KB per unit, at the cost of reconstructing Datasets per worker from a shared cache.

**Question C: Would partitioning before worker initialization reduce costs?**

Yes. Partitioning would reduce:
- Startup serialization: initargs from ~2.5 MiB to proportional fraction.
- Deserialization: per-worker graph from ~6.3 MiB to proportional fraction.
- Worker memory: per-worker retained objects proportional to assigned units.

However, it would also:
- Require redesigning `_initialize_worker` to accept partitioned data.
- Shift the cost to partitioning logic and potentially per-unit Dataset reconstruction.

**Question D: Would this optimization matter for the current ERN workloads?**

The reference executor already slices by 100 cohorts. Each `parallel_execute()` call receives 18,000 units. Per-worker deserialized memory is ~6.3 MiB. Total across 8 workers: ~53 MiB. **This does not materially affect the target studies.**

**Question E: Would it matter for the generic framework when studies become substantially larger?**

Potentially. A study with 10,000 cohorts × 180 configs = 1,800,000 units would produce ~180 MiB initargs per worker (extrapolated from measured data). Across 8 workers: ~1.4 GiB. This would warrant optimization but is not a current concern.

### E.12 Conclusion

The IO / serialization / ProcessPool audit is closed. The current **data-loading, serialization, batching, and worker-memory architecture is acceptable for the target studies.** Overall runtime bottlenecks have not yet been established by an end-to-end runtime profile.

**The evidence establishes:**

- No SQL queries or source-data file opens occur per cohort, per unit, or per month during simulation. Source datasets are loaded into memory rather than repeatedly read from disk. Process workers do perform plan-payload pickle deserialization during worker initialization; this is measured separately under serialization/IPC (§E.4–E.5) and is not per-cohort source-data IO.
- `materialize_research_plan()` constructs the full plan once.
- `parallel_execute()` passes the complete plan through `ProcessPoolExecutor` initialization.
- Pickle memoization eliminates 99.9% of duplication inside the serialized object graph (36 MiB actual vs 29.7 GiB naive).
- The reference executor partitions into 100-cohort slices (18,000 units, ~2.5 MiB initargs per slice).
- Per-worker deserialized memory is ~6.3 MiB for 100-cohort slices, ~53 MiB across 8 workers.
- Linux `fork()` provides transient COW sharing, but `_initialize_worker` unpickles independent copies, so COW does not provide a durable shared-data architecture.

**Five cost categories kept explicitly separate:**

| Category | Description | Current status |
|----------|-------------|---------------|
| **A. Mathematical work** | Monthly simulation recurrence, policy decisions, horizon chaining | Where computational reduction belongs (e.g., multi-horizon derivation) |
| **B. Execution overhead** | Worker creation, IPC, serialization, context construction, task scheduling | Measured; process parallelism and integer dispatch implemented |
| **C. IO / data access** | Disk/database/network reads | Not a major bottleneck; datasets loaded into memory, not read per unit |
| **D. Serialization / IPC** | Pickling, unpickling, initargs, task payloads, result transfer | Measured; memoization effective; summary-only mode reduces returns |
| **E. Memory amplification** | Duplicated object graphs across processes | Measured; 53 MiB total for reference executor path; non-blocking |

**Architectural consequence:**

> Do not introduce shared memory, a worker cache, a new dataset service, or a generic batching abstraction merely because such mechanisms could theoretically be faster.

There is currently no measured evidence that they are necessary for the target studies. They would add substantial architectural complexity and should only be introduced if a runtime benchmark demonstrates that serialization, worker initialization, or memory amplification is actually material.

**The next architectural priority is not IO optimization. It is the implementation of the now-decided temporal semantics that determine how the proposed studies are represented correctly.**

---

## F. Dependency Graphs

### F.1 Research Dependency Graph

```
                    ern_swr_h720.json
                    (all 5 studies)
                           │
              ┌────────────┼────────────┐
              │            │            │
         ern_cape_    is_ath/      ern_real_returns
         1871_2016    is_underwater   1871_2016
         (Part 19,20)  (Part 19,20,  (Part 42)
                        Part 52)
```

| Data Input | Part 19 | Part 20 | Part 42 | Part 49 | Part 52 |
|------------|---------|---------|---------|---------|---------|
| `ern_swr_h720.json` | ✓ | ✓ | ✓ | ✓ | ✓ |
| CAPE data | ✓ | ✓ | — | — | — |
| ATH tracking | ✓ (active GP) | ✓ (active GP) | — | — | ✓ (timing) |
| Real returns | ✓ (via dataset) | ✓ (via dataset) | ✓ (via dataset) | ✓ (via dataset) | ✓ (via dataset) |
| FFR data | — | — | — | — | ✓ (DEFERRED) |
| Contribution data | — | — | ✓ (parameter) | — | — |

### F.2 Capability Dependency Graph

```
Part 19 ────────→ Glidepath Allocation Policy
    │
    ▼
Part 20 ────────→ (extends Part 19 glidepaths, no new capability)

Part 42 ────────→ Pre-Retirement Accumulation

Part 49 ────────→ Required debt state transitions
                       │
                       ▼
                  Temporal semantics
                       │
                       ▼
                  Architectural representation decision
                  ├── policy/research layer
                  ├── execution state
                  ├── domain concept
                  └── engine extension only if proven necessary
                       │
                       ▼
                  Part 49 implementation
                       │
                       ▼
                  Part 52 extension (timing, repayment, FFR)
```

### F.3 Architectural Prerequisite Graph

```
Methodology verification (§A.1–A.5)
        │
        ▼
Temporal / event semantics audit (§D)
        │
        ├───────────────┐
        ▼               ▼
   Glidepath          OMY
   temporal           semantic
   semantics          specification
        │               │
        ▼               ▼
   P19/P20           P42

        Debt temporal semantics
                │
                ▼
     Required debt state transitions
                │
                ▼
     Architectural representation decision
        ├── policy/research layer
        ├── execution state
        ├── domain concept
        └── engine extension only if proven necessary
                │
                ▼
               P49
                │
                ▼
          Timing leverage
          temporal semantics
          + FFR investigation
                │
                ▼
               P52
```

### F.4 Per-Track S0 Dependencies

| Track | Required S0 items | Status |
|-------|------------------|--------|
| P19/P20 | Glidepath timing, `is_underwater` market-state timing | READY — 2 items DECIDED (S0-F1) |
| P42 | Contribution timing, period_index mapping, pre-retirement semantic specification | READY — 3 items DECIDED (S0-F2, S0-F3, S0-F4) |
| P49 | Loan draw timing, interest accrual timing, LTV evaluation, engine change proof | READY — 4 items DECIDED (S0-F5, S0-F6) |
| P52 | All P49 items + drawdown evaluation, repayment timing, FFR investigation | READY — 6 items DECIDED (S0-F5, S0-F6), 1 item DEFERRED (FFR) |

**FFR investigation is non-blocking for P19, P20, P42, P49.** It is blocking only for P52.

---

## G. Recommended Implementation Order

### Architecture

```text
Study / Grid Specification
        │
        ▼
ResearchPlan
        │
        ├── cohorts
        ├── parameter configurations
        ├── horizons
        └── resolved dataset references
                │
                ▼
        Execution Scheduler
                │
        ┌───────┴────────┐
        │                │
   partitioning       horizon
   / workers          chaining
        │                │
        └───────┬────────┘
                ▼
        canonical Decimal engine
```

Dataset materialization occurs before execution. No shared-memory, worker cache, or generic batching abstraction is introduced.

### Per-Stage Gate

Every stage follows:

```text
methodology specification
        ↓
independent semantic/oracle model
        ↓
implementation
        ↓
per-cohort validation
        ↓
published-anchor validation
        ↓
performance validation (stage-appropriate)
        ↓
regression gate
```

A stage that does not yet introduce meaningful executable workload may explicitly state: **Performance benchmark not yet meaningful at this stage.** Do not introduce artificial benchmarks merely to satisfy the generic lifecycle.

### S0 — Temporal and Execution Semantics

**Nature:** Semantic investigation and specification phase. **Not an implementation phase.**

**Objective:** Close all blocking temporal questions. Define exact monthly event ordering for every study. Define the boundary between research-layer planning and engine execution. Establish which requirements can be implemented entirely above the engine.

**Performance gate:** Not yet meaningful at this stage. No executable workload is introduced.

**S0 scope — permitted activities:**

- Source inspection
- Methodology reconstruction
- Independent calculations
- Small standalone oracle scripts
- Controlled experiments
- Comparison of competing temporal models
- Temporary instrumentation where necessary
- Documentation of conclusions

**S0 scope — prohibited activities:**

- Production feature implementation
- Changes to `src/engine/**`
- Changes to `ResearchPlan`
- Changes to YAML contracts
- Changes to CLI behavior
- Changes to worker architecture
- Changes to persistence
- Permanent instrumentation
- Commits

Temporary investigation artifacts must not become production changes unless separately authorized later.

### Critical S0 Requirement: Temporal Oracle Quality

**Published aggregate results alone are insufficient to resolve temporal semantics.**

For example, if two possible interpretations are:

```text
A: withdrawal → glidepath → market return
B: withdrawal → market return → glidepath
```

and both happen to produce similar published aggregate SWR values, matching the aggregate value does not establish which interpretation is correct.

> The S0 oracle must be capable of distinguishing competing temporal interpretations, rather than merely reproducing published aggregate results.

Where the ERN article does not explicitly specify the ordering, the investigation should seek the strongest available evidence from the methodology, underlying spreadsheet/calculation structure, historical trajectory behavior, and independently reconstructable examples.

If the evidence genuinely cannot distinguish two interpretations, the roadmap must record the ambiguity explicitly rather than silently choosing one.

### S0 Items to Close

| Item | Study | Classification | Status |
|------|-------|---------------|--------|
| Glidepath timing in pipeline | P19/20 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F1) |
| `is_underwater` market-state timing | P19/20 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F1) |
| Part 42 horizon interpretation | P42 | REQUIRES SPECIFICATION | DECIDED (S0-F2) |
| Contribution intra-month timing | P42 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F3) |
| period_index mapping | P42 | REQUIRES VERIFICATION | DECIDED (S0-F4) |
| Pre-retirement semantic specification | P42 | REQUIRES SPECIFICATION | DECIDED (S0-F2, S0-F3, S0-F4) |
| Loan draw timing | P49/52 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F5) |
| Interest accrual timing | P49/52 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F5) |
| LTV evaluation point | P49/52 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F5) |
| Drawdown evaluation timing | P52 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F5) |
| Repayment timing | P52 | REQUIRES ORACLE VERIFICATION | DECIDED (S0-F5) |
| FFR source, coverage, transformation | P52 | REQUIRES MEASUREMENT | DEFERRED (non-blocking for P19–P49) |
| Engine change necessity | P49/52 | REQUIRES ARCHITECTURAL PROOF | DECIDED (S0-F6) |
| IO/serialization/ProcessPool behavior | All | PICKLE-MEASURED — see §E | CLOSED |

### S0 Item Details

#### Glidepath Timing (P19/20)

**Competing interpretations:**

```text
A: period_index advance → policy decision → market return applied
B: market return applied → period_index advance → policy decision
```

plus the subsidiary question of whether ATH/underwater status uses the market state before or after the current month's return.

**S0 must establish:** Which calendar-month market state is observable by the policy decision, and whether ERN evaluates ATH/underwater status using the market state before or after that month's return. The verification must establish not merely that `is_underwater` is mathematically correct, but **which historical snapshot is used by the decision in a given month.**

#### Part 42 Horizon Interpretation

**Competing interpretations:**

```text
A: 360 total calendar months = 12 months OMY + 348 months retirement
B: 12 months OMY + 360 months retirement = 372 total months
```

**S0 must establish:** Whether ERN's stated 30-year horizon means 360 total calendar months (including OMY) or 360 months of retirement after OMY.

Until S0 establishes this, the retirement duration after OMY must remain unspecified rather than being described as 29 years.

#### Debt Semantic Model vs Architectural Placement (P49)

S0 must establish two distinct things:

**A. Debt semantic model** — What happens to:
- loan balance
- interest
- draws
- repayments
- portfolio value
- LTV
- forced liquidation
- net worth

**B. Architectural representation** — Where those concepts live:
- research layer
- policy layer
- execution state
- domain model
- engine

The semantic model (A) must be established before deciding where the state belongs (B). The architectural representation decision remains DEFERRED until the semantic model is fully specified.

### S0 Exit Criteria

For each blocking item, the roadmap must contain:

1. The competing interpretations considered
2. The evidence used
3. The selected interpretation, if determinable
4. The confidence/classification
5. The exact consequence for FBF semantics
6. The oracle or test that will protect the interpretation during implementation

For unresolved questions where the available evidence is genuinely insufficient, explicitly record:

> **UNRESOLVED — INSUFFICIENT EVIDENCE**

rather than converting an inference into a verified fact.

### S0 Completion Rule

Every item classified as a prerequisite for a study must be **CLOSED** before that study's implementation stage starts. Items that are genuinely non-blocking may remain **DEFERRED**, but must be explicitly classified as non-blocking and must not be required for the affected stage. A prerequisite cannot be closed by deferring it.

### S0 Gate

All P19/20 items closed → authorize S1. P42 items closed → authorize S3. P49 items closed → authorize S4. P52 items closed (including FFR) → authorize S6.

**Current status:**

```text
S0 semantic decisions: DECIDED (all six findings)
S0 semantic blockers: CLOSED for P19/20, P42, P49
P52: semantic decisions CLOSED, FFR investigation DEFERRED (blocking only S6)
Oracle validation: implementation-phase validation required (not an S0 semantic blocker)
S0 roadmap: READY FOR COMMIT
S1: NOT AUTHORIZED
Implementation: NOT AUTHORIZED
```

**Terminology:**

- **DECIDED** = the semantic choice has been made by the framework owner.
- **CLOSED** = the S0 prerequisite has been fully documented and its implementation protection/validation requirement is defined sufficiently for the relevant implementation stage.

For the six owner decisions, the semantic ambiguity is resolved. Oracle validation remains an implementation-phase requirement, not an S0 semantic blocker.

### Authorization Boundary

```text
Architecture approval (current status)
        │
        ▼
S0 semantic investigation
        │
        ▼
S0 review
        │
        ▼
EXPLICIT AUTHORIZATION REQUIRED
        │
        ▼
S1 implementation
```

**Architecture approval is not implementation approval.** Do not start S1. Do not modify production code. Do not modify the engine. Do not create implementation commits. The immediate objective is only to make the S0 semantic model sufficiently rigorous that, after a separate review, we can decide whether S1 should be authorized.

### S0 Investigation Findings

The following findings are based on code tracing of the FBF codebase and semantic decisions made by the framework owner. They establish what FBF currently implements and what the chosen semantics are.

#### Part 19/20 — Glidepath Temporal Semantics

**FBF pipeline ordering (STATICALLY VERIFIED):**

```
Month M entry: period_index=M, market_snapshot=dataset[M]
  Step 10: DecisionContext built from dataset[M]
  Step 20: WithdrawalDecision using DecisionContext
  Step 30: Withdrawal executed at dataset[M] prices
  Step 40: AllocationDecision using DecisionContext (frozen at Step 10)
  Step 50: Rebalance at dataset[M] prices
  Step 60: MarketEvolution — re-value holdings at dataset[M] prices
  Step 70: Capture monthly result
  Step 80: Load dataset[M+1], period_index becomes M+1
Month M exit: period_index=M+1, market_snapshot=dataset[M+1]
```

**VERIFIED:**

- FBF's current pipeline ordering is: withdrawal → allocation → market return.
- The policy at Step 40 observes `dataset[M]`.
- `is_ath`/`is_underwater` are precomputed metadata in the dataset.
- The currently identified article-level operations ("withdrawal is taken out, then the glidepath adjustment is made") are consistent with the corresponding FBF ordering.

**DECIDED (S0-F1):**

- The FBF pre-evolution observation model is the intended semantic model.
- "Underwater" refers exclusively to the S&P 500 index being below its all-time high.
- The allocation decision for month M uses the market state available at the beginning of month M.
- FBF's current mapping (policy observes `dataset[M]` for month M) is correct.

**THEREFORE:**

The semantic contract is DECIDED: the allocation decision observes the beginning-of-period S&P 500 market state. FBF's current pipeline is structurally consistent with that contract. Independent ERN-equivalence validation remains an implementation-phase requirement.

#### Part 42 — OMY Temporal Semantics

**FBF period_index-to-dataset-index mapping (STATICALLY VERIFIED):**

| period_index | dataset index | ERN notation |
|---|---|---|
| 0 | `dataset[0]` | d_{c-1} |
| 1 | `dataset[1]` | d_c |
| 12 | `dataset[12]` | d_{c+11} |
| 13 | `dataset[13]` | d_{c+12} |

The array/index mapping is verified: `period_index=M` corresponds to `dataset[M]`. A 30-year horizon requires 361 observations (T+1 = 360+1). The initial portfolio is priced at `dataset[0]`.

**DECIDED (S0-F2, S0-F3, S0-F4):**

- **Horizon interpretation:** 360 total months = 12 months OMY + 348 months retirement. Do NOT model as 12 + 360 = 372 months.
- **Contribution timing:** Contributions occur before the monthly market return. A January contribution participates in the January → February market evolution.
- **period_index economic meaning:** period_index 0–11 = 12 complete OMY working/contribution months. period_index 12 = first retirement month.

**Baseline structure (STATICALLY VERIFIED):**

The baseline (non-OMY) uses `horizon_years * 12 + 1` observations: `+1` is the base snapshot `d_{-1}`, NOT an OMY month. The reference oracle uses `T=360` retirement months for a 30-year horizon. The dataset naming `h360` = 360 retirement months.

**FBF structural mapping:** VERIFIED — `period_index` and dataset indices are well-defined.
**ERN temporal equivalence:** VERIFIED — the specific month-to-phase mapping and economic meaning are DECIDED.

#### Part 49/52 — Debt Temporal Semantics

**FBF debt state (STATICALLY VERIFIED):**

- No `loan_balance`, `interest_rate`, `ltv_ratio`, or `net_worth` fields in `SimulationState`.
- No debt fields in `DecisionContext`. Policies cannot observe loan state.
- No debt-related code anywhere in `src/` or `tests/`.
- `Portfolio` holds only positive `AssetHolding` units — no liability holdings.
- `current_wealth` means gross portfolio value, not net worth.

**Pipeline gap analysis (STATICALLY VERIFIED):**

| Debt Operation | Nearest Pipeline Step | Market State Observed | Gap |
|---|---|---|---|
| Loan draw | Would extend Step 30 | Current-month prices | NO EXISTING STEP |
| Interest accrual | Would parallel Step 60 | Inflation/FFR data | NO EXISTING STEP |
| LTV evaluation | Would need new step | Current-month prices | NO EXISTING STEP |
| Drawdown evaluation | Would parallel Step 10/40 | `is_ath`, `is_underwater` | NO EXISTING STEP |
| Repayment | Would extend Step 30 | `is_ath` | NO EXISTING STEP |

**DECIDED (S0-F5, S0-F6):**

- **Debt temporal ordering:** Debt becomes active immediately upon borrowing. Interest is accrued at end of period.
- **DecisionContext interaction:** Allocation policies observe the beginning-of-period state. The DecisionContext should expose debt and leverage information for leverage-aware strategies.

**FBF structural mapping:** VERIFIED — pipeline gaps identified.
**ERN temporal equivalence:** VERIFIED — the specific month-to-phase mapping and economic meaning are DECIDED.

**Methodology reconstruction (VERIFIED from articles):**

The articles establish the following for Part 49:
- Loan is "drawn continuously from month 1" — initial draw at the start of retirement
- Interest is "capitalized" — added to loan balance, not paid out of pocket
- Rates are fixed real (CPI-adjusted)
- LTV constraint: `balance / portfolio_value <= 0.75` "at all times"
- No repayment
- Net worth = Portfolio Value − Loan Balance

For Part 52, additionally:
- Drawdown trigger: S&P 500 TR index 20%+ below ATH
- Conditional draws: Borrow% of budget from margin loan
- Repayment: at fresh ATH, double withdrawal, excess pays loan
- LTV constraint tightened to 0.50
- FFR + spread for interest rate

**DECIDED (S0-F5, S0-F6):**

- **Loan draw timing:** Debt becomes active immediately upon borrowing.
- **Interest accrual timing:** Interest is accrued at end of period.
- **LTV evaluation point:** Debt is subject to margin-call conditions from the moment it is borrowed.
- **DecisionContext interaction:** Allocation policies observe the beginning-of-period state. The DecisionContext should expose debt and leverage information.

**FBF structural mapping:** ALL DEBT OPERATIONS ARE GAPS.
**ERN temporal equivalence:** VERIFIED — the specific month-to-phase mapping and economic meaning are DECIDED.

### S0 Structured Findings

The following findings use the structured format required by the S0 gate. Each question is explicitly documented with competing interpretations, evidence, and confidence level.

#### Finding S0-F1: Part 19/20 Underwater Market-State Timing

**Status: DECIDED — HIGH CONFIDENCE**

**Question:** Which market state does ERN use for the is_underwater condition in the glidepath methodology?

**Decision:** The FBF pre-evolution observation model is the intended semantic model.

**Rationale:**

"Underwater" refers exclusively to the **S&P 500 index being below its all-time high**. It does not refer to:
- the simulated portfolio,
- portfolio drawdown,
- the user's allocation,
- individual assets,
- or allocation performance.

The allocation decision for month M uses the market state available at the beginning of month M:

```text
January market state
        ↓
January allocation decision
        ↓
January → February market return
        ↓
Updated February market state
        ↓
February allocation decision
```

The January → February return cannot affect the January decision because that return has not yet occurred.

**ERN methodology fact:** The article establishes that the underwater check uses the S&P 500 TR index "measured at the last closing date of the month."

**FBF semantic decision / owner-defined contract:** The pre-evolution observation model correctly implements the temporal logic: a decision made at the beginning of month M cannot depend on the market return that occurs during month M.

**Implementation consequence:** FBF's current mapping (policy observes `dataset[M]` for month M) is correct. No pipeline reordering or look-ahead mechanism is required.

**Validation requirement:** Verify that the existing dataset indexing correctly maps the dataset snapshot to the beginning-of-period market state. This is an implementation/data-index verification, not an unresolved economic interpretation.

**Confidence:** HIGH — explicit framework-owner semantic decision

#### Finding S0-F2: Part 42 Horizon Interpretation

**Status: DECIDED — HIGH CONFIDENCE**

**Question:** Does the 30-year horizon mean 360 total calendar months (12 OMY + 348 retirement) or 360 retirement months after OMY (12 OMY + 360 retirement = 372 total)?

**Decision:** Use the ERN interpretation: 360 total months.

```text
360 total months
    = 12 months working/contributing
    + 348 months retirement
```

Do **not** model it as 12 + 360 = 372 months.

**ERN methodology fact:** The article states "30-year horizon" and "12 months" OMY. The baseline (non-OMY) uses 360 retirement months.

**FBF semantic decision / owner-defined contract:** The 30-year horizon includes the OMY period. The total is 360 months: 12 working months + 348 retirement months.

**Implementation consequence:**
- Total dataset observations required: 361 (360 months + 1 base snapshot)
- Retirement months after OMY: 348
- The `horizon_months` parameter value for OMY cohorts: 361
- The baseline and OMY share the same total horizon (360 months)

**Validation requirement:** Verify that the implementation correctly uses 348 retirement months for OMY cohorts.

**Confidence:** HIGH — explicit framework-owner semantic decision

#### Finding S0-F3: Part 42 Contribution Timing

**Status: DECIDED — HIGH CONFIDENCE**

**Question:** Does the $5k contribution happen before or after market returns within the same month?

**Decision:** Contributions occur **before the monthly market return**.

```text
Beginning of month
      ↓
Contribution
      ↓
Market exposure
      ↓
Monthly market return
      ↓
End of month
```

A January contribution therefore participates in the January → February market evolution.

**ERN methodology fact:** The article states "$5,000/month" contributions but does not explicitly specify the intra-month ordering.

**FBF semantic decision / owner-defined contract:** Contributions occur before market returns. This is consistent with the baseline pipeline order (withdrawal → allocation → market evolution) and with the economic principle that contributions are invested at the beginning of the month.

**Implementation consequence:**
- The contribution earns that month's return
- The effective growth rate of the contribution includes that month's return
- The portfolio value at the start of retirement reflects the contribution plus one month of growth

**Validation requirement:** Verify that the implementation correctly applies the contribution before the market return.

**Confidence:** HIGH — explicit owner decision

#### Finding S0-F4: Part 42 period_index Economic Meaning

**Status: DECIDED — HIGH CONFIDENCE**

**Question:** What does period_index=12 represent in the OMY context — the last OMY month or the first retirement month?

**Decision:** Define the economic interpretation as:

```text
period_index 0–11
    = 12 complete OMY working/contribution months

period_index 12
    = first retirement month
```

Combined with the 360-month total horizon:

```text
12 working months
+
348 retirement months
=
360 total months
```

Do not introduce an alternative "29-year retirement" abstraction into the roadmap. The implementation should work from explicit month counts and the defined phase transition.

**ERN methodology fact:** The article does not explicitly state what period_index=12 represents economically.

**FBF semantic decision / owner-defined contract:** period_index 0–11 are the 12 OMY working/contribution months. period_index 12 is the first retirement month. This is consistent with the 360-month total horizon (12 + 348 = 360).

**Implementation consequence:**
- period_index 0–11: contributions occur, no withdrawals
- period_index 12: first withdrawal, no contributions
- The dataset is sliced so that period_index=0 is the base snapshot (d_{c-1})

**Validation requirement:** Verify that the implementation correctly transitions from contribution mode to withdrawal mode at period_index=12.

**Confidence:** HIGH — explicit owner decision

#### Finding S0-F5: Part 49/52 Debt Temporal Ordering

**Status: DECIDED — HIGH CONFIDENCE**

**Question:** What is the exact temporal ordering of debt operations relative to market evolution, withdrawals, and other pipeline steps?

**Decision:** Debt is part of the active financial state of the period from the moment it is borrowed.

A newly borrowed amount:
- becomes active immediately,
- can immediately be used as a withdrawal/funding source,
- is immediately subject to margin-call conditions,
- and remains part of the portfolio/debt state during the current period.

Interest is accrued **at the end of the period**.

Therefore, if debt is borrowed during January:

```text
January borrowing
      ↓
Debt active during January
      ↓
January market/portfolio evolution
      ↓
January interest accrual
      ↓
Updated debt becomes February's beginning state
```

One important nuance: Do **not** encode an unnecessarily rigid ordering between every individual operation yet. The semantic decisions that are fixed are:
- Borrowing → debt becomes active immediately
- Interest → accrued at end of period

The exact ordering of borrowing versus other operations should be specified per methodology where required.

**ERN methodology fact:** The articles establish the required debt operations (draw, interest, LTV check, repayment) but do not explicitly specify the intra-month ordering.

**FBF semantic decision / owner-defined contract:** Debt becomes active immediately upon borrowing. Interest is accrued at end of period. This is consistent with the economic principle that borrowed funds are immediately available and subject to margin conditions.

**Implementation consequence:**
- Debt operations fit in the pipeline as new steps or extensions of existing steps
- Market state is available at each debt operation
- The DecisionContext interaction is resolved (see S0-F6)

**Validation requirement:** Verify that the implementation correctly makes debt active immediately and accrues interest at end of period.

**Confidence:** HIGH — explicit owner decision

#### Finding S0-F6: Part 49/52 DecisionContext Interaction

**Status: DECIDED — HIGH CONFIDENCE**

**Question:** Does the methodology require allocation decisions to observe the post-withdrawal/post-debt portfolio, or is the beginning-of-period decision state intentional?

**Decision:** Option C — Allocation policies observe the **beginning-of-period state**, but the decision context should expose the information required for leverage-aware strategies.

Conceptually:

```text
Beginning-of-period financial state
        ↓
DecisionContext
    ├── portfolio
    ├── debt
    ├── net equity
    ├── leverage information
    └── relevant market state
        ↓
Allocation policy
```

The policy does not wait for end-of-period accounting to make its allocation decision.

This means the previous `DecisionContext` concern should **not** automatically be treated as a defect. Instead, the architectural question becomes:

> Can the existing `DecisionContext` represent the required beginning-of-period leverage state without violating its existing semantics?

If not, determine the **smallest** necessary extension during implementation planning. Do not redesign it pre-emptively.

**ERN methodology fact:** The article does not explicitly state whether allocation should observe pre- or post-modification state.

**FBF semantic decision / owner-defined contract:** Allocation policies observe the beginning-of-period state. The DecisionContext should expose debt and leverage information for leverage-aware strategies. This is consistent with FBF's current design and does not require architectural changes.

**Implementation consequence:**
- DecisionContext may need extension to expose debt/leverage information
- No pipeline reordering required
- No architectural redesign required

**Validation requirement:** Verify that the implementation correctly exposes debt/leverage information in DecisionContext and that allocation policies can access this information.

**Confidence:** HIGH — explicit owner decision

### S0 Oracle Gap Analysis

The six S0 findings are now DECIDED. This section documents the oracle requirements for validating the implementation against published ERN values.

#### Current Oracle Inventory

| Oracle | Location | Coverage | Limitations |
|--------|----------|----------|-------------|
| Reference oracle | `tools/ern/reference_oracle.py` | Basic SWR depletion (Part 49 Table 1) | No glidepaths, no OMY, no leverage |
| Pinned oracle matrix | `data/ern/p49_oracle_table.csv` | 5×9×4 static allocation SWR | Only FV=0, no temporal variations |
| Timeline regression test | `tests/oracle/ern/test_ern_timeline_regression.py` | Pipeline step order verification | No semantic validation of temporal interpretations |
| ERN SWR Toolbox Google Sheet | External (not in codebase) | Original ERN calculations | Requires manual access |

**Conclusion:** The reference oracle covers only basic SWR depletion. Oracles for glidepaths, OMY, and leverage must be developed.

#### Oracle Requirements for Validation

The purpose of the oracle is now to validate that the implementation correctly implements the **chosen semantics** and reproduces the expected ERN published results.

```text
Before:
semantic ambiguity
      ↓
need oracle to choose interpretation

Now:
explicit semantic contract
      ↓
implement
      ↓
independent oracle
      ↓
verify mathematical behavior
      ↓
compare published anchors
```

**S0-F1: Part 19/20 Underwater Market-State Timing**

| Required Oracle | Purpose | How to Obtain |
|----------------|---------|---------------|
| Glidepath SWR table | Compute SWR for glidepath policies using pre-evolution `is_underwater` | Extend `reference_oracle.py` to implement glidepath allocation logic |
| Comparison against ERN published values | Validate implementation matches published glidepath SWR values | Access ERN Part 19/20 articles or Google Sheet for published glidepath SWR tables |

**S0-F2: Part 42 Horizon Interpretation**

| Required Oracle | Purpose | How to Obtain |
|----------------|---------|---------------|
| OMY SWR (360 total months) | Compute SWR for OMY with 12 months contributions + 348 months retirement | Extend `reference_oracle.py` to implement OMY contributions |
| Comparison against ERN published values | Validate implementation matches published OMY SWR values | Access ERN Part 42 article or Google Sheet for published OMY SWR values |

**S0-F3: Part 42 Contribution Timing**

| Required Oracle | Purpose | How to Obtain |
|----------------|---------|---------------|
| OMY SWR (contribution before return) | Compute SWR where contributions earn that month's return | Extend `reference_oracle.py` to implement OMY with contribution-before-return |
| Comparison against ERN published values | Validate implementation matches published OMY SWR values | Access ERN Part 42 article or Google Sheet for published OMY SWR values |

**S0-F4: Part 42 period_index Economic Meaning**

| Required Oracle | Purpose | How to Obtain |
|----------------|---------|---------------|
| OMY SWR (period_index 0–11 = working months) | Compute SWR where period_index=12 is first retirement month | Extend `reference_oracle.py` to implement OMY with this convention |
| Comparison against ERN published values | Validate implementation matches published OMY SWR values | Access ERN Part 42 article or Google Sheet for published OMY SWR values |

**S0-F5: Part 49/52 Debt Temporal Ordering**

| Required Oracle | Purpose | How to Obtain |
|----------------|---------|---------------|
| Leverage SWR (debt active immediately, interest at end) | Compute SWR where debt becomes active immediately and interest accrues at end of period | Extend `reference_oracle.py` to implement leverage with chosen semantics |
| Comparison against ERN published values | Validate implementation matches published leverage SWR values | Access ERN Part 49/52 articles or Google Sheet for published leverage SWR values |

**S0-F6: Part 49/52 DecisionContext Interaction**

| Required Oracle | Purpose | How to Obtain |
|----------------|---------|---------------|
| Leverage SWR (allocation observes beginning-of-period state) | Compute SWR where allocation uses beginning-of-period state with debt/leverage info | Extend `reference_oracle.py` to implement leverage with chosen semantics |
| Comparison against ERN published values | Validate implementation matches published leverage SWR values | Access ERN Part 49/52 articles or Google Sheet for published leverage SWR values |

#### Oracle Development Strategy

**Phase 1: Article Extraction**

Extract published SWR values from ERN articles for each study:
- Part 19/20: Glidepath SWR tables
- Part 42: OMY SWR values
- Part 49/52: Leverage SWR values

This provides the comparison targets for oracle validation.

**Phase 2: Minimal Oracle Development**

Build minimal oracles for each study:
- Implement the chosen semantics
- Compare against published values
- Validate mathematical correctness

This provides the validation mechanism for each study.

**Phase 3: Integration**

If minimal oracles cannot validate a study, escalate to full oracle development or external resource acquisition.

#### Implementation Consequence

The oracle gap does not block implementation. The six findings are now DECIDED, and implementation can proceed based on the chosen semantics.

The roadmap distinguishes between:

**Oracle-dependent work:** Implementation whose validation requires oracles. This includes:
- Glidepath policy validation (requires glidepath SWR oracle)
- OMY contribution validation (requires OMY SWR oracle)
- Debt/leverage validation (requires leverage SWR oracle)

**Design-independent of oracle:** Implementation that can be designed from the decided semantic contract without an oracle. This includes:
- Glidepath policy logic (implementation based on chosen semantics)
- OMY contribution mechanism (implementation based on chosen semantics)
- Debt/leverage operations (implementation based on chosen semantics)
- Oracle development tooling
- Test harness infrastructure
- Pipeline step framework extensions
- Domain model extensions for debt concepts

**Implementation correctness:** Still requires unit/invariant tests and, where applicable, independent oracle/published-anchor validation. The semantic decision establishes the design contract, not acceptance of the implementation.

### S1 — Part 19 Glidepath Capability

**Prerequisite:** S0 P19/20 items CLOSED.

**Objective:** Implement the minimum generic glidepath capability required by the methodology. Prefer a period-indexed/stateless representation where possible.

**VERIFIED methodology:** See §A.1.

**Engine changes:** NONE required unless the existing pipeline demonstrably cannot represent the required semantics.

**Validation:** Passive and active glidepath semantics against independent methodology reconstruction. Benchmark against existing static-allocation baseline.

**Validation anchors (from §A.1):** Failsafe SWR for 80% static: 3.14%. 60→100% glidepath, CAPE > 20: 3.47% (vs 3.25% static).

**Performance gate:** Benchmark glidepath execution against static-allocation baseline. Expected: comparable runtime per cohort (glidepath adds one policy decision per month).

**Risk Level:** LOW

### S2 — Part 20 Extension

**Prerequisite:** S1 complete.

**Objective:** Reuse Part 19 capability. Add the additional horizons, CAPE regimes, and glidepath variants required by Part 20.

**VERIFIED methodology:** See §A.2.

**Engine changes:** NONE.

**Validation:** Independently rather than tuning to published headline values.

**Risk Level:** LOW

### S3 — Part 42 Accumulation

**Prerequisite:** S0 P42 items CLOSED (semantic specification, contribution timing, period_index mapping).

**Objective:** First implement the research-level semantic model. Establish the exact relationship between accumulation and retirement. Only introduce an engine-level contribution mechanism if the research-layer representation cannot express the required mathematics cleanly.

**VERIFIED methodology:** See §A.3.

**Engine changes:** REQUIRES ARCHITECTURAL PROOF. Only if research-layer approach is insufficient.

**If both representations exist:** Require numerical equivalence tests against the canonical Decimal oracle.

**Validation anchors (from §A.3):** 30y baseline failsafe: ~3.6%. OMY with contributions: +7.8%.

**Performance gate:** Benchmark accumulation phase against baseline. Expected: 12-month accumulation adds negligible overhead relative to the retirement simulation.

**Risk Level:** MEDIUM

### S4 — Part 49 Debt Foundation

**Prerequisite:** S0 P49 items CLOSED.

**Objective:** Define the debt state transition model first. Resolve draw timing, interest accrual, withdrawals, LTV evaluation, forced liquidation, and net-worth semantics. Prove whether the existing engine can represent these transitions without violating its domain boundaries. Only then authorize any engine change.

**VERIFIED methodology:** See §A.4.

**Architectural representation decision (DEFERRED — REQUIRES ARCHITECTURAL PROOF):** Driven by temporal ordering, LTV evaluation, state lifetime, policy access, domain purity, engine interface sufficiency.

**Engine changes:** REQUIRES ARCHITECTURAL PROOF.

**Validation anchors (from §A.4):** 1929 near wipeout at month 238. 1965 partial leverage LTV below 70%.

**Performance gate:** Not yet meaningful at this stage. Debt foundation defines the semantic model; execution performance depends on S5 implementation choices.

**Risk Level:** MEDIUM-HIGH

### S5 — Part 49 Leverage Execution

**Prerequisite:** S4 complete.

**Objective:** Implement leverage using the validated debt model. Validate per-cohort trajectories and published anchor scenarios. Preserve the Decimal engine as the canonical oracle.

**VERIFIED methodology:** See §A.4 (3% portfolio + 1% loan = 4% total).

**Performance gate:** Benchmark leverage execution against non-leverage baseline. Expected: debt state tracking adds overhead per month (interest accrual, LTV check), but order-of-magnitude comparable.

**Risk Level:** MEDIUM

### S6 — Part 52

**Prerequisite:** S0 P52 items CLOSED (including FFR investigation), S4 complete, S5 complete.

**Objective:** Add drawdown-triggered borrowing. Add repayment semantics. Resolve FFR data transformation and monthly alignment. Validate solver requirements only after the underlying simulation semantics are deterministic.

**VERIFIED methodology:** See §A.5.

**Performance gate:** Benchmark timing-leverage execution against Part 49 baseline. Expected: drawdown evaluation and repayment add conditional logic per month, comparable runtime.

**Risk Level:** MEDIUM

---

## H. Validation Strategy

### H.1 Oracle Strategy

| Study | Independent Oracle | Published Anchors | Per-Cohort |
|-------|-------------------|-------------------|------------|
| Part 19 | YES | Failsafe SWR tables (§A.1) | YES (1,700+) |
| Part 20 | YES | Failsafe SWR, percentile tables (§A.2) | YES (1,700+) |
| Part 42 | YES | SWR improvement % (§A.3) | YES (all cohorts) |
| Part 49 | PARTIAL | Case study results (§A.4) | LIMITED (2 cohorts) |
| Part 52 | PARTIAL | WR + Borrow% tables (§A.5) | LIMITED (2 cohorts) |

### H.2 Validation Discipline

1. Independent methodology reconstruction
2. Independent oracle (where feasible)
3. FBF implementation
4. Per-cohort comparison
5. Published-result comparison (as validation anchors, not tuning targets)
6. Regression protection

---

## I. Data Strategy

### I.1 Existing Data

All five studies can use `ern_swr_h720.json` for base returns. CAPE data sufficient for Parts 19/20.

### I.2 FFR Dataset Investigation (DEFERRED)

See §C.6. Non-blocking for P19–P49. Blocking only for P52.

### I.3 Data Provenance Requirements

JSON format with version field, provenance file, no runtime network access, frozen before execution.

---

## J. Engine Change Assessment

### J.1 Principle

> The Decimal reference engine remains the canonical mathematical oracle. Its mathematical behavior must not be altered merely for performance.

### J.2 Capability-by-Capability Assessment

| Capability | Can it live above engine? | Engine change needed? | Status |
|------------|--------------------------|----------------------|--------|
| Glidepath allocation | YES (policy layer) | NO | RESOLVED |
| Pre-retirement (research-layer) | CANDIDATE | No engine change currently expected | REQUIRES PROOF |
| Pre-retirement (engine-level) | CANDIDATE | YES — contribution step | REQUIRES ARCHITECTURAL PROOF |
| Debt state | UNVERIFIED | UNVERIFIED | REQUIRES ARCHITECTURAL PROOF |
| Leverage withdrawal | UNVERIFIED | UNVERIFIED | REQUIRES ARCHITECTURAL PROOF |
| Timing trigger | UNVERIFIED | UNVERIFIED | REQUIRES ARCHITECTURAL PROOF |
| Repayment logic | UNVERIFIED | UNVERIFIED | REQUIRES ARCHITECTURAL PROOF |
| FFR dataset | TBD | No engine change currently expected | REQUIRES INVESTIGATION |

### J.3 No Engine Changes Authorized

No engine modification is authorized until:
1. Higher-layer approaches are demonstrated insufficient.
2. The exact change is specified with scope, behavior, and regression tests.
3. The user explicitly authorizes the change.

---

## K. Open Architectural Questions

### K.1 Glidepath Timing Semantics

**Status: DECIDED (S0-F1)**

The semantic decision is established: the allocation decision observes the beginning-of-period S&P 500 market state. FBF's current pipeline is structurally consistent with that contract.

**Implementation validation:** Verify that the dataset snapshot supplied to the allocation decision represents the beginning-of-period market state. Independent ERN-equivalence validation remains an implementation-phase requirement.

### K.2 Active Glidepath ATH Semantics

**Status: DECIDED (S0-F1)**

"Underwater" means the S&P 500 real total-return index is below its ATH. It is a market-index condition, not a portfolio-level or allocation-level condition.

**Implementation validation:** Verify that the glidepath policy correctly uses the beginning-of-period market state for the underwater condition.

### K.3 Pre-Retirement Semantic Specification

**Status: DECIDED (S0-F2, S0-F3, S0-F4)**

The semantic decisions for Part 42 are established:
- 360 total months = 12 working months + 348 retirement months
- Contributions occur before market returns
- period_index 0–11 = working months, period_index 12 = first retirement month

**Implementation validation:** Numerical equivalence proof is an implementation-phase acceptance criterion. The research-layer and engine-level formulations must be validated to represent the same process.

### K.4 Part 42 Horizon Interpretation

**DECIDED (S0-F2):**

```text
360 total months
    = 12 months working/contributing
    + 348 months retirement
```

Do **not** model it as 12 + 360 = 372 months.

### K.5 Debt Model Placement

**Status:** DEFERRED — after temporal ordering and state transitions are understood.

### K.6 Solver/Optimization Approach

**Status:** DEFERRED — manual sweep sufficiency unverified.

### K.7 Part 42 Contribution Timing

**Status: DECIDED (S0-F3)**

The semantic decision is established: contributions occur before the monthly market return. A January contribution participates in the January → February market evolution.

**Implementation validation:** Verify that the implementation correctly applies the contribution before the market return.

---

## L. Risk Register

| Risk | Severity | Probability | Mitigation |
|------|----------|-------------|------------|
| Temporal ordering mismatch | HIGH | MEDIUM | S0 oracle verification per study |
| Glidepath policy breaks determinism | HIGH | LOW | Unit tests, same context → same decision |
| Debt state violates domain purity | HIGH | LOW | Architectural proof determines placement |
| Pipeline step ordering bugs | MEDIUM | MEDIUM | Validate against article, test interactions |
| Fast path eligibility breaks | HIGH | LOW | Explicit eligibility check |
| Pre-retirement look-ahead bias | HIGH | MEDIUM | Historical returns for accumulation only |
| Research/engine equivalence unverified | MEDIUM | MEDIUM | Semantic spec before; numerical proof after |
| FFR transformation error | MEDIUM | MEDIUM | Full investigation (§C.6) before materialization |
| Cross-process memory amplification | LOW | LOW | Measured: 53 MiB total for reference executor 100-cohort slices; non-blocking |

---

## M. Glossary

| Term | Definition |
|------|-----------|
| **Glidepath** | Dynamic asset allocation changing over time during retirement |
| **Passive glidepath** | Equity weight increases by fixed slope each month |
| **Active glidepath** | Equity weight increases only when market is below ATH |
| **Failsafe SWR** | Minimum historical SWR across all cohorts |
| **OMYS** | One More Year Syndrome |
| **Margin loan** | Brokerage loan secured by portfolio assets |
| **LTV** | Loan-to-Value ratio |
| **FFR** | Federal Funds Rate |
| **ATH** | All-Time High |
| **Borrow%** | Share of retirement budget funded by margin loan |
| **Sequence Risk** | Risk of poor returns early in retirement |
| **Calendar horizon** | Total simulation duration in months |
| **Retirement period** | Months during which withdrawals occur |
| **Accumulation period** | Months during which contributions occur |

---

**END OF ROADMAP**
