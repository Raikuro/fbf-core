# Design Rationale

This document explains *why* the FBF architecture is shaped the way it does.
For what the architecture *is*, see [ARCHITECTURE.md](../ARCHITECTURE.md).

---

## Priority Hierarchy

All design decisions are evaluated against this ordering:

1. **Correctness** — mathematical precision over convenience.
2. **Reproducibility** — identical inputs produce identical outputs, always.
3. **Traceability** — audit trails for all decisions.
4. **Extensibility** — clean seams for new policies and strategies.
5. **Performance** — never at the cost of the above.

Performance is explicitly last. Optimisations are opt-in, empirically
validated, and never alter default behaviour.

---

## Reference Decimal Engine as Semantic Oracle

The reference monthly pipeline (`decimal.Decimal`, step-by-step) is the
**canonical source of truth** for simulation correctness. Both the closed-form
fast path and the chained execution strategy are *derived* from it and must
produce bit-equivalent results.

This design exists because:

* SWR research requires exact arithmetic — float rounding produces
  unbounded accuracy-conformance surface.
* The 180-cell ERN oracle acceptance matrix is pinned to exact `Decimal`
  equality. Any discrepancy is a defect, not a tolerance issue.
* Having a single reference engine makes correctness verifiable by
  construction rather than by sampling.

The fast path validates against the reference. Chaining reuses reference
results. Neither replaces the reference.

---

## Chaining

Multi-horizon study grids have prefix-consistent datasets: shorter horizons
are prefix subsets of the longest horizon. Chaining executes only the
longest-horizon context per family, then derives shorter horizons by
truncation.

**Why it exists:** It reduces month-work by exactly 3× (e.g. 169M → 56M
months) without any correctness sacrifice. Derived results reuse identical
`MonthlySimulationResult` objects and `Decimal` statistics.

**Why slice-based dispatch is mandatory:** Whole-plan chained
materialization would hold ~0.37 MiB per unit, extrapolating to ~110 GiB
for a full grid. Sliced dispatch bounds peak per-worker memory. Slices are
cohort-aligned (cohorts never split) to preserve horizon families. Result
merging is order-preserving, making sliced execution equivalent to
whole-plan.

---

## Parallel Execution

The parallel execution invariant is:

```
parallel_execute(plan, workers=k) ≡ sequential_execute(plan)   for all k ≥ 1
```

This is a hard correctness requirement, not a performance aspiration.

**Why deterministic batching:** Work is distributed by batch (not individual
units). `batch_size = ceil(len(units) / workers)`. Same plan + same worker
count → same batch assignment → same results.

**Why batch-order collection:** Results are collected in batch order (not
completion order). This guarantees the final ordering matches `plan.units`
exactly, regardless of worker scheduling.

**Why worker isolation:** Worker processes are pure functions — no side
effects, no database access, no inter-process communication. This prevents
deadlock and ensures determinism.

---

## Repository Separation

The core/CLI split exists because:

* The simulation engine is independently reusable — it has no inherent
  coupling to terminal UI, argument parsing, or YAML file formats.
* Zero third-party runtime dependencies for Core means it can be embedded
  in any Python environment without conflict.
* Independent release control: CLI can release without requiring Core
  changes, and Core can be consumed by alternative front-ends.
* The dependency direction is strictly one-way: external consumers depend on
  Core; Core never knows about any consumer.

---

## Domain Purity

The domain layer (`fbf.core.domain`) must never import from execution,
study, optimization, persistence, or CLI.

**Why:** The domain contains the value objects and policy interfaces that
define the problem space. If domain objects depended on execution or
infrastructure, they could not be reasoned about independently, tested in
isolation, or reused in alternative execution contexts.

Domain objects are constructed from primitive data. They never acquire
datasets, never access the filesystem, and never perform I/O.

---

## Immutability

All domain objects are frozen dataclasses by default. Only `SimulationState`,
`Portfolio`, and `AssetHolding` are mutable — and only during explicit state
transitions within the pipeline.

**Why:** Immutability makes state transitions explicit and auditable. It
prevents hidden mutation, enables safe sharing across workers (the same
`Dataset` and `MarketSnapshot` objects can be referenced by thousands of
simulations without duplication), and makes the simulation deterministic by
construction. Hidden mutation would make results depend on execution order,
which is unacceptable for reproducible research.

The separation between **Configuration** (immutable: Dataset, AllocationPolicy,
WithdrawalPolicy, Horizon, Target) and **State** (mutable: Portfolio,
Allocation, Accumulated Withdrawal) is absolute. They must never be mixed.
`ExperimentDefinition` is completely immutable and never contains results.
`SimulationResult` is constructed exactly once at simulation end and never
modified.

---

## Two-Domain Split

The system is split into two conceptually distinct domains that must never
cross-contaminate:

* **Engine** — executes simulations. It knows only generic financial and
  simulation concepts (Portfolio, Allocation, Withdrawal, Dataset, Simulation).
  It never knows about specific studies, EarlyRetirementNow, or any particular
  experiment.
* **Research** — defines scientific studies. It describes which simulations
  must be executed, never implements simulation logic, and expresses everything
  through configuration using only Engine capabilities.

This separation ensures the simulation engine is reusable for any retirement
research, not just the original ERN studies. New research can be defined
without modifying the engine.

---

## Error Isolation

A failure in one simulation must never cause the failure of other simulations
in the same experiment run. Errors are logged. Recoverable errors (invalid
dataset, wrong configuration, nonexistent cohort) are reported via validation
results. Non-recoverable errors terminate only the corresponding execution.

**Why:** Research grids may contain thousands of simulation units. A single
bad configuration in one unit should not destroy hours of computation in
others.

---

## Policy Abstraction

Policies are pure decision functions. They receive a `DecisionContext`
(immutable snapshot of current state) and return a `PolicyDecision`. They
never modify state, never perform I/O, and never depend on execution or
infrastructure.

**Why:** This separation keeps strategies swappable without touching
execution logic. A withdrawal policy can be changed without modifying the
pipeline. An allocation policy can be tested in isolation.

Policy lifecycle: `before_simulation → before_month → decide → after_month →
after_simulation`. Same `DecisionContext` must produce identical
`PolicyDecision`.

---

## Performance Principles

* **Profile before optimising.** Measure with benchmarks, change one thing
  at a time.
* **Document every optimisation.** Record what changed and why.
* **Correctness before performance.** Engine, research, and optimization
  layers are frozen; never trade correctness for speed.
* **Opt-in only.** Performance modes (fast path, chaining) are activated
  explicitly and never affect default behaviour.
* **Memory boundedness.** Plan-build RSS is measured. Parallel memory is
  bounded by slice sizing. Whole-plan materialization is explicitly
  prohibited when extrapolation exceeds available RAM.

---

## Persistence Design

SQLite is the initial persistence implementation because it is file-based,
requires no server, supports concurrent reads, and provides transactional
durability. However, the domain never depends on persistence implementation
details. The same simulation engine can run without SQLite, without YAML,
without CSV, using only in-memory objects.

**Schema philosophy:** The database stores only results, never serves as a
data source during simulation. Normalized tables (no serialized blobs when
normalization is possible). All Decimal values stored as strings to avoid
floating-point precision loss. Policy parameters stored as JSON. Dates as
ISO 8601.

**Schema evolution:** A version-tracking table records applied migrations.
Schema changes create new versions with migration scripts; existing schema is
never modified in place. Every persisted result stores simulator version,
dataset version, and schema version for provenance.

**Codec pattern:** New persisted types require a corresponding encoder/
decoder. Lossless round-trip is mandatory: every domain object persisted and
retrieved must be field-for-field identical.

**Write concurrency:** SQLite allows only one writer at a time. Writes are
serialized while reads can be parallelized. WAL mode and synchronous NORMAL
provide durability with acceptable performance.

**Soft deletion:** Implemented via `deleted_at` columns. Restoration requires
semantic equivalence of content fields (name, revision, description, dataset
configuration, policy definitions), not ID matching. Storage-generated UUIDs
are incidental to identity.

---

## API Philosophy

The facade (`fbf.core`, Tier 1) is the curated public surface intended for
external consumers. It re-exports the essential types and functions needed to
configure, execute, and persist simulations without reaching into internal
modules.

**What is intentionally not public:** Tier 3 modules (internal pipeline
steps, study internals) are implementation details. The executor exposes no
API for executing monthly pipeline steps, calculating financial values, or
constructing statistics directly.

**Compatibility:** Public interfaces remain stable between minor versions.
Breaking changes require a minor version increment. The facade does not expose
persistence internals, optimization algorithms, or pipeline step details.

**Conceptual guarantees:** External consumers can rely on the facade to
provide configuration, execution, and persistence. Anything not exported
through the facade is subject to change without notice.

---

## Deliberately Rejected Approaches

* **Float fast path for production use:** Rejected because it creates an
  unbounded accuracy-conformance surface. The reference engine remains the
  semantic oracle; the fast path validates against it.
* **Whole-plan sequential chaining:** Rejected due to ~110 GiB memory
  extrapolation. Slice-based dispatch is mandatory.
* **Base/fallback policy scalar duality:** Rejected in favour of a
  universal arrays-only model. The Cartesian product of three value arrays
  is the sole materialization path.
* **`parameters` section in study config:** Rejected. The arrays-only model
  eliminates base/fallback redundancy and precedence ambiguity.
* **Grid-ness inferred from shape:** Rejected. Exactly one
  policy-resolution rule applies to all study kinds.
* **Independent whole-horizon reference execution:** Rejected. Reference
  chaining is bit-exact and makes the independent path redundant.

---

## Non-Goals (Deliberately Out of Scope)

The following are explicitly excluded from the framework:

* Real-time trading or live data feeds
* Multi-currency support
* Behavioral finance modelling
* Tax optimization
* Monte Carlo stochastic simulation
* Interactive UI or web dashboards
* Machine learning predictions
* High-frequency data

Keeping scope tight is a deliberate architectural decision. Each excluded
capability would fundamentally alter the architecture.
