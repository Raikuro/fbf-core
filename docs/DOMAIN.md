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

### Study Configuration (`StudyConfiguration`)

A complete study specification: metadata, allocation and withdrawal policy
axes, horizon axes, optional cohort bounds, and optional final-value targets.
`StudyConfiguration` is the normalized YAML interpretation layer and is
immutable once constructed. It contains no results, portfolio state, or
statistics.

Planning materializes the configuration into a `ResearchPlan` of
`PlannedSimulationUnit` values. Execution consumes a pipeline
`ExperimentDefinition`, which carries an ordered tuple of simulation contexts
and does not itself own results.

### Cohort

A historical start date within a study. Each cohort represents a different
starting point in the dataset, enabling analysis across market conditions.

### Planned Simulation Unit (`PlannedSimulationUnit`)

One materialized simulation request within a `ResearchPlan`: a cohort, scalar
parameter configuration, concrete allocation and withdrawal policies, an
initial portfolio, a cohort-sliced dataset, and a horizon. Optional fields carry
evaluation targets, cash-flow schedules, and Part 49 debt parameters. Units are
independent — the order in which they execute never affects results.

### Portfolio

An immutable snapshot of asset ownership at a point in time. A `Portfolio`
contains a sequence of `AssetHolding` values; each holding pairs an `AssetClass`
with a `units` quantity.

**Valuation:**
At a given `MarketSnapshot`, each holding's value is
`units × MarketSnapshot.index_levels[asset_class]`. Total portfolio value is the
sum of those values over all holdings. `index_levels` provide the per-unit index
level for each asset; the `Portfolio` itself stores no monetary values.

**Invariants:**
1. Holding units are non-negative.
2. Total wealth equals the sum of `units × index_level` over all holdings at the
   valuation snapshot.
3. Derived allocation weights sum to exactly 100% within the domain's `Decimal`
   arithmetic.
4. Portfolio operations do not create or destroy wealth.

`Portfolio` and `AssetHolding` are frozen dataclasses and are never mutated.
Withdrawals, rebalances, and market evolution are executed by the domain services
`PortfolioWithdrawalService`, `PortfolioRebalanceService`, and
`PortfolioMarketEvolutionService`; each returns a new `Portfolio`.

### AssetClass

An abstract category of financial asset, such as an equity or government-bond
index. Identifies a time series within a Dataset. Never stores money or
portfolio state and contains no simulation logic.

### Dataset and MarketSnapshot

A **Dataset** is a collection of historical time series (one per AssetClass),
loaded and validated before simulation begins. Completely immutable and
shared by all simulations.

A **MarketSnapshot** is an immutable point-in-time market state for a single
month: date, per-AssetClass index levels used to value holdings, monthly and
cumulative inflation, running all-time-high, underwater status, and optional
CAPE. Never contains portfolio information.

---

## Policies

### What Policies Do

Policies make decisions. Services execute those decisions. A Policy is a pure
decision function: it receives a `DecisionContext` (immutable snapshot of
current state) and returns a `PolicyDecision`.

### What Policies Must Not Do

* Modify Portfolio
* Touch SQLite or any persistence layer
* Perform portfolio operations
* Depend on execution or infrastructure

### Policy Contract

The current policy contract is a single operation:
`decide(context: DecisionContext) -> PolicyDecision`. The earlier lifecycle
hooks are not present in the implementation. Policies may read the dataset
through the supplied `DecisionContext`, but they return decisions rather than
mutating portfolio or persistence state.

Given the same `DecisionContext`, a Policy must produce the exact same
`PolicyDecision`. This is the determinism contract.

### AllocationPolicy

Decides the target allocation (which percentage of wealth should be in each
asset class). Returns an `AllocationDecision`.

Current implementations are `ConstantAllocationPolicy`,
`GlidepathAllocationPolicy`, and `BuyAndHoldAllocationPolicy`. The YAML-visible
`AllocationPolicyType` enum exposes `CONSTANT`, `GLIDEPATH`, and
`BUY_AND_HOLD`.

### WithdrawalPolicy

Decides the withdrawal amount (nominal and real). Returns a
`WithdrawalDecision`.

Current implementations are `FixedRealWithdrawalPolicy`,
`ConstantWithdrawalPolicy`, `Part49WithdrawalPolicy`,
`Part52WithdrawalPolicy`, and `EscalatingWithdrawalPolicy`. The YAML-visible
`WithdrawalPolicyType` enum exposes `FIXED_REAL`, `CONSTANT`, `PART49`,
`PART52`, and `ESCALATING`.

---

## Simulation State

Mutable simulation execution state belongs to the execution pipeline:
`fbf.core.execution.pipeline.simulation.SimulationState`. It carries the
execution context, portfolio and allocation state, decisions, status, debt
state, and accumulated monthly results.

The domain layer defines immutable value objects, policy contracts, and pure
domain services. It does not define a parallel simulation state or parallel
simulation result contracts.

---

## Timeline and Results

The simulation timeline, result, statistics, and experiment contracts are
defined by the execution pipeline in
`fbf.core.execution.pipeline.simulation`.

### SimulationTimeline

A chronological, ordered collection of MonthlyResult objects — one per
simulated month. No duplicates, no gaps.

### MonthlyResult

A complete immutable snapshot of a simulation at the end of a period:
time, market state, portfolio state, allocation and withdrawal decisions,
return and drawdown metrics, events, and optional debt or net-cash-flow data.
It contains the information needed to reconstruct the simulation at that point.

### SimulationResult

The final immutable result of one simulation, containing a
`SimulationTimeline` and `SimulationStatistics`. An `ExperimentRun` aggregates
results for an `ExperimentDefinition`.

### SimulationStatistics

Final wealth, maximum drawdown, success and failure state, failure month,
simulated months, and execution time. `SimulationStatistics` is frozen and
assembled from the completed simulation; policies never touch it.

---

## Numerical Precision

All monetary values use `decimal.Decimal`. Never float. One centralized
rounding policy for the entire project. All comparisons between monetary
values use Decimal. Derived statistical metrics may use other numeric
representations where explicitly appropriate.

---

## Reproducibility

Given the same code, Dataset, configuration, and execution definition, results
must be identical. Execution order of simulations never affects results.
Production execution uses the single Numba plan executor. The database never modifies a result — it only
stores information.
