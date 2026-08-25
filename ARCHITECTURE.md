# FBF Architecture — FIRE Backtesting Framework

This document describes the high-level architecture of the FIRE Backtesting
Framework (FBF): the responsibilities of each repository, the public API
boundary, the dependency direction, and the local development workflow.

For design rationale and rejected alternatives, see
[docs/DESIGN.md](./docs/DESIGN.md).
For durable architectural decisions, see [docs/DECISIONS.md](./docs/DECISIONS.md).

---

## 1. Priority Hierarchy

All design decisions are evaluated against this ordering:

1. **Correctness** — mathematical precision over convenience.
2. **Reproducibility** — identical inputs produce identical outputs, always.
3. **Traceability** — audit trails for all decisions.
4. **Extensibility** — clean seams for new policies and strategies.
5. **Performance** — never at the cost of the above.

Performance is explicitly last. Optimisations are opt-in, empirically
validated, and never alter default behaviour.

## 2. Repository Overview

The FBF system is split into two standalone Git repositories that are
**peers with no parent Git repository**:

```
/workspace/
├── fbf-core/          — simulation engine and research library (this repo)
└── <consumer>/        — external consumer (e.g. a CLI, web app, or notebook)
```

There is **no umbrella `fbf/.git`** and no monorepo layer.

---

## 3. fbf-core — Simulation Engine

### 3.1 Responsibility

`fbf-core` is the computation and research library. It owns:

* **Domain model** — value objects (`Money`, `Portfolio`, `Asset`, `Dataset`,
  market snapshots, decision contexts) with deterministic `Decimal` arithmetic.
* **Policy interfaces** — abstract protocols for withdrawal and allocation
  decisions; concrete built-in implementations (`FixedRealWithdrawalPolicy`,
  etc.).
* **Canonical nine-step monthly simulation pipeline** — the ordered sequence of
  steps executed per calendar month:
  1. Initialize Allocation (seeds initial allocation for month 0)
  2. Build Decision Context
  3. Withdrawal Decision
  4. Withdrawal Execution
  5. Allocation Decision
  6. Portfolio Rebalance
  7. Market Evolution
  8. Monthly Result Builder
  9. Simulation State Update

  Statistics accumulation is a post-pipeline concern handled by
  `SimulationStatisticsBuilder` after the simulation loop completes.
* **Closed-form fast path** — analytical recurrence for constant-policy studies,
  validated to be bit-exact against the reference pipeline.
* **Multi-horizon execution** — deterministic multi-worker execution for
  prefix-consistent multi-horizon grids.
* **Simulation executor** — application-layer coordinator only. No financial
  model, no monthly execution, no statistics. Delegates to `SimulationRunner`
  via dependency injection. One public operation: `execute(experiment) →
  ExperimentResult`.
* **Study planning** — cohort generation, parameter sweeps, experiment
  definitions. Plans are fully materialized before execution; no plan
  construction during execution.
* **SWR optimisation** — binary-search solver for maximum safe withdrawal rates.
  Domain-agnostic optimizer; architecture permits alternative solvers without
  modifying the engine.
* **Persistence** — SQLite-backed study repository (codecs, schema, context).
  Domain never knows persistence implementation; SQLite is swappable.
* **ERN oracle** — canonical Decimal truth table for regression testing.

### 3.2 What fbf-core must NOT contain

* Any import from any CLI package or external-consumer package.
* Argument parsing, `argparse`, `sys.argv` access, or presentation logic.
* `pyyaml` at runtime (YAML is an optional, lazily imported convenience; the
  caller is expected to own the YAML dependency).
* UI progress display, formatting utilities, or console escape sequences.

---

## 4. External Consumers

`fbf-core` is independently usable and may be consumed by any application
that needs FIRE simulation capabilities. External consumers include CLI
front-ends, web applications, notebooks, and other Python libraries.

The dependency direction is strictly one-way:

```
External consumers
       │
       ▼
   fbf-core
       │
       ▼
Python stdlib only
```

Core never imports from any consumer. Consumers import through Tier 1 or
Tier 2 only.

---

## 5. Public Core API Boundary

The Core API is organised in three access tiers:

| Tier | Modules | Access |
|------|---------|--------|
| **Tier 1** | `fbf.core` (root facade) | All consumers |
| **Tier 2** | `fbf.core.domain`, `fbf.core.domain.model`, `fbf.core.domain.policies`, `fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence` | Consumers with explicit need |
| **Tier 3** | `fbf.core.study.internal`, `fbf.core.execution.pipeline.steps`, and all other non-facade submodules | Core tests only |

External consumers are **forbidden** from importing Tier 3 modules. Core
tests may freely test implementation details.

### 5.1 Tier 1 Public Surface

Tier 1 (`fbf.core`) is the **curated public surface intended for external
consumers**. It re-exports the essential types and functions needed to
configure, execute, and persist simulations without reaching into internal
modules.

The exact exported symbol set is authoritative in the package (`fbf.core.__all__`)
and guarded by the `test_public_facade_symbols` contract test. This document
describes the boundary and purpose; the package remains authoritative for the
complete symbol list.

---

## 6. Dependency Direction

```
External consumers  ──depends on──►  fbf-core  ──► Python stdlib only
```

* `fbf-core` has **zero third-party runtime dependencies**. It runs exclusively
  on the Python 3.13 standard library.
* The dependency arrow is **strictly one-directional**. Core never imports
  from any consumer.

### 6.1 Import Law

| Importer | May import |
|----------|-----------|
| `fbf.core.*` | Python stdlib; other `fbf.core.*` submodules (no upward domain violations) |
| External consumers | Python stdlib; `fbf.core` Tier 1 & Tier 2; consumer-owned dependencies |
| Consumer tests | Same as external consumers |
| Core tests | Python stdlib; all of `fbf.core.*` including Tier 3 |

---

## 7. Layer Isolation Rules (enforced by contract tests)

1. **Domain purity:** `fbf.core.domain` must never import `fbf.core.execution`,
   `fbf.core.study`, `fbf.core.optimization`, or `fbf.core.persistence`.
2. **Execution / optimization isolation:** `fbf.core.execution` must never
   import `fbf.core.optimization`.
3. **Consumer→Core direction:** External consumers may only import Core via
   Tier 1 or Tier 2.
4. **No legacy imports:** No `engine.*`, `research.*`, `infrastructure.*`, or
   old `cli.*` imports may appear in any production source file.

These rules are enforced by automated AST contract tests in each repository's
`tests/contract/` directory.

---

## 8. Repository Interaction

`fbf-core` is an independently installable Python package:

```bash
pip install fbf-core    # installs simulation engine only
```

For local development:

```bash
pip install -e .
```

Consumers declare their own dependency on `fbf-core` with an appropriate
version constraint. Breaking Core API changes (during 0.x development)
require a Core minor version increment.

---

## 9. Local Development Workflow

### 9.1 One-time setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate

# Install fbf-core in editable mode
pip install -e .
```

### 9.2 Running tests

```bash
# Full test suite
pytest -p no:cacheprovider

# Type checking
mypy --strict src
```

### 9.3 Linting

```bash
ruff check src tests
```

### 9.4 Building distribution artifacts

```bash
python -m build --wheel
```

---

## 10. Key Invariants

1. `fbf-core` is usable without any specific consumer installed.
2. `fbf-core` has zero third-party runtime dependencies.
3. Monetary values use `decimal.Decimal` — no `float` for `Money` objects or
   monetary domain operations. Derived statistical metrics may use other numeric
   representations where explicitly appropriate.
4. The Decimal fast path is bit-exact against the reference monthly pipeline.
   The Float fast path is approximate and opt-in.
5. ERN oracle acceptance matrix passes with exact `Decimal` equality (no float tolerance).
6. External consumers import exclusively through the public Core API (Tier 1 and Tier 2).
7. No history is rewritten in either repository after the initial migration commit.
8. **Determinism:** `parallel_execute(plan, workers=k) ≡ sequential_execute(plan)` for all k ≥ 1.
9. **Domain purity:** `fbf.core.domain` never imports from execution, study, optimization, persistence, or CLI.
10. **Policy determinism:** Same `DecisionContext` produces identical `PolicyDecision`.
11. **Portfolio invariant:** Total wealth equals sum of asset holdings; no negative holdings; allocation sums to 100%.
12. **Executor boundary:** `SimulationExecutor` is an application-layer coordinator only — no financial model, no pipeline steps, no statistics.
13. **Trajectory identity:** A trajectory is defined by (start cohort/date, allocation parameters, withdrawal parameters, initial wealth, initial portfolio, other state-affecting simulation inputs). Evaluation-only dimensions such as `final_value_target` MUST NOT participate in trajectory identity and MUST NOT cause additional trajectory execution. See [docs/DECISIONS.md](./docs/DECISIONS.md#evaluation-dimensions-vs-simulation-dimensions).

## 11. Dataset Distribution & Ownership Model

Datasets are **not** shipped in the `fbf-core` wheel; they are external artifacts consumed
through the generic **Dataset Directory** contract (a directory of `<identifier>.json`
files, identified by filename stem, versioned by an in-file `version` field). Dataset
resolution, loading, and process-local caching are owned by fbf-core
(`persistence.studies.sqlite`: `DatasetCache`, `DefaultDatasetResolver`,
`_load_datasets_from_dir`; study-facing resolver `fbf.core.study.builder.resolve_dataset`).
The CLI is a pass-through for `--data-dir` only. Installed-only deployments must supply a
Dataset Directory explicitly. See [DATASETS.md](./DATASETS.md) for the full decision and
contract.

---

## 12. Execution Data Flow

Simulation execution operates on materialized, immutable dataset data prepared
before task execution.

Workers operate on the materialized experiment data supplied by the execution
layer and do not independently resolve or reload datasets from persistence for
individual simulation tasks.

Simulation execution does not access persistence or SQL. Persistence is a
separate concern outside the simulation execution path.

Performance analysis distinguishes three independent optimization categories:

1. mathematical work;
2. execution overhead;
3. data-access/IO.

Optimization decisions must be based on measurement rather than assuming that
an improvement in one category addresses another.

---

## 13. Persistence

The persistence layer provides SQLite-backed storage for study results. Key
properties:

* **Domain independence:** The domain never knows persistence implementation.
  SQLite is swappable for PostgreSQL, DuckDB, Parquet, or CSV by implementing
  new Repository adapters.
* **Schema ownership:** The infrastructure layer owns the schema. The domain
  never references table names, columns, or SQL.
* **Write serialization:** SQLite allows one writer at a time. Writes are
  serialized; reads are parallelized. WAL mode and synchronous NORMAL provide
  durability.
* **Soft deletion:** Entities are soft-deleted via `deleted_at` columns.
  Restoration requires semantic equivalence of content fields, not ID matching.
* **Schema evolution:** A version-tracking table records applied migrations.
  Schema changes create new versions; existing schema is never modified in place.
* **Codec pattern:** New persisted types require encoder/decoders. Lossless
  round-trip is mandatory: every domain object persisted and retrieved must be
  field-for-field identical.
* **Decimal storage:** All Decimal values stored as strings to avoid
  floating-point precision loss.

See [docs/DESIGN.md](./docs/DESIGN.md) for persistence design rationale.

---

## 14. Architectural Principles

### Specification-Driven Development

Specifications define contracts. Code implements them. Tests validate them.
If code and documentation disagree, the specification is the authority;
correct the code or propose a specification update. Never silently redefine
unspecified behaviour.

### Immutability by Default

Value objects are frozen dataclasses. State transitions are explicit. Hidden
mutation should be avoided. Referential transparency is the goal.

### Policy Abstraction

Policies make decisions. Services execute those decisions. Policies should not
contain execution actions merely to simplify a particular implementation.
This separation keeps strategies swappable without touching execution logic.

Policy lifecycle: `before_simulation → before_month → decide → PolicyDecision
→ after_month → after_simulation`. Same `DecisionContext` must produce
identical `PolicyDecision`. Policies are stateless; all state resides in
`DecisionContext` (immutable snapshot).

### Deterministic Execution

Identical inputs must produce identical outputs unless nondeterminism is
explicitly part of the modeled behaviour. This applies to simulation runs,
parallel execution, and all domain computations.

### YAGNI

Before introducing a new abstraction, extensibility point, hook, strategy,
callback, or generic interface, demonstrate that it is required by the current
specification or an approved milestone. Potential future use cases alone are
insufficient justification.
