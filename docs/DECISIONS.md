# Architectural Decisions

Compact records of decisions whose rationale should be preserved. Not every
decision belongs here — only those where a future maintainer might plausibly
make the wrong choice if the reasoning were absent.

Decisions owned by external consumers are documented in their respective
repositories.

---

## Semantic Equivalence for Soft-Delete Restoration

**Decision:** Persistence IDs are storage-generated UUIDs, incidental to
identity. Restoration of a soft-deleted entity requires semantic equivalence
of content fields, not ID matching.

**Why:** Matching ID alone could resurrect unrelated rows. Content fields
(name, revision, description, dataset configuration, policy definitions)
determine identity. Timestamps, UUIDs, duration measurements, and simulation
results are excluded — they are provenance or outputs, not configuration.

**Alternatives rejected:** ID-based restoration — rejected because
storage-generated UUIDs have no semantic relationship to entity identity.

**Consequence:** Any future persisted entity must define its own explicit
equivalent-field set.

---

## Arrays-Only Configuration Model

**Decision:** Study configurations use arrays of values for parameterized
studies. No base/fallback/override duality. No `parameters` section. The
sole materialization path is the Cartesian product of three value arrays
(`nominal_rates`, `real_rates`, `inflation_rates`). `StudyConfiguration`
has a singular `dataset:` field and a mandatory `policy.type`.

**Why:** The configuration model with a `parameters` section and base
scalars with array overrides creates ambiguity about precedence. The
arrays-only model is simpler: `equity_allocation: [0.60, 0.75, 0.90]`
produces a Cartesian product of all value arrays.

**Alternatives rejected:** A plural/fallback model with aliases and
deprecation shims — rejected because the arrays-only model is simpler and
eliminates precedence ambiguity.

**Consequence:** Single materialization path for all study kinds. Single-value
studies use one-element arrays. The `optimize` command requires exactly one
value per array. No backward compatibility with earlier configuration formats.

---

## Reference Chained Execution

**Decision:** The execution model uses reference chaining — execute the
longest horizon per family, derive shorter horizons by truncation. Chaining
splits into cohort-aligned slices, dispatches via parallel execution, and
merges back in plan order.

**Why:** 3× month-work reduction without correctness sacrifice (e.g. 169M →
56M months). Derived results reuse identical objects. Bit-exact with
independent execution on the full 313,020-unit ERN grid. Slice-based
dispatch is mandatory because whole-plan chained materialization would hold
~0.37 MiB per unit, extrapolating to ~110 GiB for a full grid.

**Alternatives rejected:** Maintaining an independent whole-horizon
reference execution path — rejected because chaining is bit-exact and makes
the independent path redundant. Whole-plan sequential chaining — rejected
due to memory exhaustion at scale.

**Consequence:** Two execution paths share the chaining architecture:
reference chained (full Decimal pipeline, bit-exact, default) and fast path
(float closed-form recurrence, approximate, opt-in via `--fast-path`).
Both use slice-based dispatch for memory safety. Cohort alignment preserves
horizon family grouping. No independent (unchained) reference execution
path exists.

---

## Policy Instance Sharing

**Decision:** Reuse one policy instance per distinct parameter value instead
of creating fresh per-unit objects.

**Why:** In a parameterized study, many simulation units share the same
policy parameter values. Creating separate objects for each unit wastes
memory (626k objects reduced to ~14 distinct instances, plan-build RSS
reduced 46%).

**Alternatives rejected:** Fresh per-unit object creation — rejected due to
excessive memory consumption.

**Consequence:** Policies must be stateless for this to be safe.

---

## Frozen Layers

**Decision:** The engine layer, research layer, and optimization layer are
frozen. New behaviour is added only through the infrastructure and CLI layers.

**Why:** Freezing the core layers prevents accidental coupling between
simulation semantics and presentation. Extension points exist at defined
seams (policy interfaces, strategy protocols, persistence codecs).

**Alternatives rejected:** Extending engine/research/optimization layers
with presentation logic — rejected because it would entangle simulation
semantics with I/O concerns.

**Consequence:** Any new capability must be expressed through policy
interfaces, strategy protocols, or persistence codecs — never by modifying
the simulation pipeline directly.

---

## ERN Oracle as Canonical Ground Truth

**Decision:** The 180-cell ERN oracle acceptance matrix is the definitive
mathematical ground truth. The engine source (`src/engine/**`) is never
modified. Any new execution path — including the decimal fast path — must
reproduce the oracle bit-for-bit using identical per-month, per-asset
Decimal arithmetic (withdrawal ratio, negative-unit clamp, canonical
rebalance order, residual closure).

**Why:** SWR research requires exact arithmetic — float rounding produces
unbounded accuracy-conformance surface. The 180-cell ERN oracle acceptance
matrix is pinned to exact `Decimal` equality. Any discrepancy is a defect,
not a tolerance issue. Having a single reference engine makes correctness
verifiable by construction rather than by sampling.

**Alternatives rejected:** Tolerance-based equivalence — rejected because
the architecture demands exact identity for Decimal execution paths.
Algebraic recurrences that diverge at exact-equality depletion boundaries
are insufficient; the arithmetic order must replicate the reference exactly.

**Consequence:** The ERN E2E gates are opt-in (environment-gated) and
remain the final arbiter of correctness. The decimal fast path produces
identical results to the reference engine on all fields. Float boundary
divergences are documented and pinned.
