# Domain Model

This document describes the domain concepts of the FIRE Backtesting Framework,
their relationships, and the invariants that must be preserved. For
architectural structure, see [ARCHITECTURE.md](../ARCHITECTURE.md). For
design rationale, see [DESIGN.md](./DESIGN.md).

---

## Two Domains

The system contains two conceptually distinct domains:

* **Engine** — executes simulations using generic financial concepts
  (Portfolio, Allocation, Withdrawal, Dataset, Simulation). It never knows
  about specific studies or experiments.
* **Research** — defines scientific studies describing which simulations
  must be executed. It never implements simulation logic.

This separation ensures the engine is reusable for any retirement research.

---

## Core Concepts

### Study (ExperimentDefinition)

A complete experiment specification: name, description, dataset reference,
horizon, allocation policies, withdrawal policies, and optimization targets.
Immutable once created. Contains no results, no portfolio state, and no
statistics.

### Cohort

A historical start date within a study. Each cohort represents a different
starting point in the dataset, enabling analysis across market conditions.

### SimulationUnit

One independent simulation: a single combination of cohort, allocation
policy, withdrawal policy, and target. Units are independent — the order
in which they execute never affects results.

### Portfolio

The economic state of a portfolio at a given instant. Contains a list of
AssetHoldings (each: AssetClass + euro value) and total wealth.

**Invariants:**
1. Total wealth equals the sum of all asset holdings.
2. No asset holding may be negative.
3. Allocation sums to exactly 100% (within rounding tolerance).
4. No money is created or destroyed by any operation.

Portfolio stores euros, never shares or units. All modifications go
exclusively through PortfolioService.

### AssetClass

An abstract category of financial asset (e.g. ACWI Total Return EUR, Euro
Government Bonds). Identifies a time series within a Dataset. Never stores
money, knows a Portfolio, or contains logic.

### Dataset and MarketSnapshot

A **Dataset** is a collection of historical time series (one per AssetClass),
loaded and validated before simulation begins. Completely immutable and
shared by all simulations.

A **MarketSnapshot** is an immutable point-in-time market state for a single
month: date, per-AssetClass returns and index levels, monthly and cumulative
inflation, running all-time-high, and underwater status. Never contains
portfolio information.

---

## Policies

### What Policies Do

Policies make decisions. Services execute those decisions. A Policy is a pure
decision function: it receives a `DecisionContext` (immutable snapshot of
current state) and returns a `PolicyDecision`.

### What Policies Must Not Do

* Modify Portfolio
* Access the full Dataset
* Touch SQLite or any persistence layer
* Perform financial operations
* Depend on execution or infrastructure

### Policy Lifecycle

```
before_simulation(context)    — initialization
       ↓
before_month(decision_context) — pre-month setup
       ↓
decide(decision_context)       — returns PolicyDecision (immutable)
       ↓
after_month(decision_context)  — post-month bookkeeping
       ↓
after_simulation(context)      — finalization
```

Given the same `DecisionContext`, a Policy must produce the exact same
`PolicyDecision`. This is the determinism contract.

### AllocationPolicy

Decides the target allocation (which percentage of wealth should be in each
asset class). Returns an `AllocationDecision`.

Built-in implementations: Constant Allocation, Passive Glidepath, Active
Glidepath.

### WithdrawalPolicy

Decides the withdrawal amount (nominal and real). Returns a
`WithdrawalDecision`.

Built-in implementation: Constant Inflation-Adjusted Withdrawal.

---

## Simulation State

**SimulationState** is the mutable heart of a simulation. It represents only
the current instant: current date, period number, Portfolio, current
Allocation, AllocationTarget, AllocationDrift, current WithdrawalDecision,
current MarketSnapshot, current wealth, peak wealth.

It never stores historical results, statistics, or timeline. It is one of
very few mutable domain objects.

---

## Timeline and Results

### SimulationTimeline

A chronological, ordered collection of MonthlyResult objects — one per
simulated month. No duplicates, no gaps.

### MonthlyResult

A complete immutable snapshot of a simulation at the end of a period:
time, market state, portfolio state, operations, statistics, and events.
Must contain everything needed to reconstruct the simulation state at
any point in time.

### SimulationResult

Constructed exactly once at simulation end and never modified. Contains
SimulationContext (immutable config snapshot), SimulationStatistics,
SimulationTimeline, Summary, and Diagnostics.

### SimulationStatistics

Aggregate metrics: simulated months, withdrawals, rebalances, capital
withdrawn, capital traded, peak and minimum wealth, max drawdown, CAGR,
execution time. Updated automatically during simulation; policies never
touch it.

---

## Numerical Precision

All monetary values use `decimal.Decimal`. Never float. One centralized
rounding policy for the entire project. All comparisons between monetary
values use Decimal. Derived statistical metrics may use other numeric
representations where explicitly appropriate.

---

## Reproducibility

Given the same code, Dataset, Configuration, and ExperimentDefinition,
results must be identical. Execution order of simulations never affects
results. Parallelism never alters calculations. The database never modifies
a result — it only stores information.
