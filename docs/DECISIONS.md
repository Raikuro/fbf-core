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

## Multi-Horizon Execution

**Decision:** The execution model uses horizon derivation — execute the
longest horizon per family, derive shorter horizons by truncation. Derived
results reuse identical objects. Splits into cohort-aligned slices,
dispatches via parallel execution, and merges back in plan order.

**Why:** 3× month-work reduction without correctness sacrifice (e.g. 169M →
56M months). Derived results reuse identical objects. Bit-exact with
independent execution on the full 313,020-unit ERN grid. Slice-based
dispatch is mandatory because whole-plan materialization would hold
~0.37 MiB per unit, extrapolating to ~110 GiB for a full grid.

**Alternatives rejected:** Maintaining an independent whole-horizon
reference execution path — rejected because derivation is bit-exact and
makes the independent path redundant. Whole-plan sequential execution —
rejected due to memory exhaustion at scale.

**Consequence:** Both the reference engine and the fast path use the same
slice-based dispatch for memory safety. Cohort alignment preserves horizon
family grouping.

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

---

## Fast Path Three-Tier Model

**Decision:** The fast path operates in three tiers:
1. **Reference** — full Decimal pipeline, bit-exact, default, authoritative.
2. **Decimal Fast Path** — exact optimization for eligible policy family,
   proven bit-exact with the reference, retained as a performance optimization.
3. **Float Fast Path** — approximate, opt-in, non-authoritative, exploratory.

**Why:** An earlier non-essential executor variant was removed because all
CLI invocations route through the standard fast-path entry point.
Removing the redundant version simplifies the API surface and eliminates
dead code.

**Alternatives rejected:** Keeping the redundant executor for hypothetical
future use — rejected because YAGNI and the current version subsumes all
functionality.

**Consequence:** The fast-path executor inherits `SimulationExecutor`
directly. `run_fast_path_validation()` calls `evaluate_closed_form()`
directly. Tests verify equivalence against direct closed-form evaluation.

---

## Evaluation Dimensions vs Simulation Dimensions

**Decision:** `final_value_target` is an evaluation dimension, not a
simulation dimension. It MUST NOT participate in trajectory identity and
MUST NOT cause additional trajectory execution.

**Why:** A trajectory is defined by its simulation inputs: start cohort/date,
allocation parameters, withdrawal parameters, initial wealth, initial
portfolio, and other state-affecting inputs. `final_value_target` is a
post-simulation classification criterion — it determines whether a completed
trajectory "succeeded" by checking final wealth against a threshold. It does
not affect any month-by-month simulation state.

When `final_value_target` is included in the Cartesian product (as in the
ERN 900-cell grid), the planning layer expands logical units by the
number of targets (5×). However, the Reference executor correctly
deduplicates trajectory evaluation: contexts with different
`final_value_target` values but identical trajectory parameters share a
single simulation path. The FV check is applied per-target after path
evaluation.

Measured overhead of the current representation (5 FV targets vs 0):

| FV targets | Units | Worker exec | Total | Exec ratio |
|-----------|------:|------------:|------:|-----------:|
| 0 | 313,020 | 585s | 588s | 1.00x |
| 1 | 313,020 | 586s | 589s | 1.00x |
| 2 | 626,040 | 593s | 597s | 1.01x |
| 5 | 1,565,100 | 609s | 637s | 1.07x |

Worker execution time is nearly constant — the same 78,255 unique
trajectories execute regardless of FV target count. The 7% increase for
5 targets comes from additional iteration over expanded context lists,
not from trajectory re-simulation.

**Alternatives rejected:** Separating `TrajectoryPlan` from
`EvaluationPlan` — rejected because the ~8.5% overhead (50s on a 588s
run) does not justify the API complexity and correctness risk. The
existing deduplication mechanism already achieves the core optimization.

**Consequence:** Future evaluation-only dimensions (e.g., alternative
success criteria, preservation thresholds, drawdown limits) must follow
the same pattern: excluded from trajectory identity, applied per-target
after trajectory evaluation. If the overhead becomes material with many
more targets, a `TrajectoryPlan` / `EvaluationPlan` separation can be
revisited with empirical evidence.

---

## Explicit Configuration Mode for Constrained Parameter Tuples

**Decision:** The study builder supports an `allocation_policy.configurations`
list in YAML for declaring constrained parameter tuples, as an alternative to
the Cartesian product of independent axis arrays.

**Why:** Part 19/20 glidepath studies require specific `(start, end, slope,
mode)` combinations where slopes are associated with specific start/end pairs.
A Cartesian product of glidepath parameters would produce invalid combinations
(e.g., slope 0.5 for a 20pp spread that should use slope 0.2). The explicit
configurations mode eliminates this by allowing the study author to declare
exactly which combinations are valid.

**Alternatives rejected:** Filtering invalid Cartesian products post-hoc —
rejected because it obscures the study author's intent and creates silent
configuration errors. Splitting glidepath parameters into separate study
files — rejected because it fragments the study definition and complicates
aggregation.

**Consequence:** `configurations` and axis-based policy parameters are
mutually exclusive. Each explicit configuration is crossed with the remaining
study axes (withdrawal_rate, horizon_years, final_value_target). The
implementation is confined to the builder layer; the engine and domain layers
are unchanged.

---

## Binary CAPE Classification for Part 20

**Decision:** Part 20 uses a binary CAPE classification (HIGH/LOW) that is
deliberately different from the existing four-level model at the CAPE=20
boundary.

**Why:** Part 20 splits cohorts into exactly two populations for analysis:
- HIGH: CAPE > 20 (expensive market)
- LOW: CAPE <= 20 (cheap/moderate market)

The four-level model classifies CAPE=20 as HIGH (min_inclusive), while the
binary model classifies CAPE=20 as LOW (max_inclusive). This boundary
difference is intentional and reflects the article's methodology.

**Alternatives rejected:** Reusing the four-level model with post-hoc
grouping — rejected because it would not correctly implement the Part 20
binary split at CAPE=20.

**Consequence:** The `CapeBinary` enum and `classify_cape_binary()` function
coexist with the existing `CapeRegime` model. Both are independent
classification functions; neither modifies the other. Missing CAPE values
raise `ValueError` (fail-fast) rather than silently defaulting to a regime.

---

## Part 42 Accumulation Temporal Semantics

**Decision:** The Part 42 OMY study uses a research-layer pre-processing
model. The 12-month accumulation phase is computed before the retirement
simulation and produces the retirement starting portfolio. No engine
modification is required.

### Temporal Structure

The 30-year horizon is modeled as 360 total calendar months:

```
Phase 1 — Accumulation:
  period_index 0–11: 12 months
  Dataset: 13 snapshots (indices 0..12)
  Return transitions: 12 (0→1 .. 11→12)

Phase 2 — Retirement:
  period_index 12–359: 348 months
  Dataset: 349 snapshots (indices 12..360)
  Return transitions: 348 (12→13 .. 359→360)

Total:
  Dataset: 361 snapshots (indices 0..360)
  Return transitions: 360
  MonthlyResults: 360 (12 accumulation + 348 retirement)
```

**horizon_months contract:**
- `Dataset.slice(start_date, N)` returns N snapshots (indices 0..N-1 within
  the slice).
- `SimulationContext.horizon_months` specifies the number of return
  transitions to execute, producing that many `MonthlyResult` objects.
- For accumulation: `Dataset.slice(start, 13)` + `horizon_months=12`.
- For retirement: `Dataset.slice(retirement_start, 349)` +
  `horizon_months=348`.

**period_index mapping:** The retirement context uses local period indices
starting at 0. The study-level month 12 corresponds to local period 0; study
month 359 corresponds to local period 347. This is intentional — the engine
is not modified to preserve global study-level indices.

### Unit System

The simulation operates in a currency-neutral unit system. The ERN study is
specified in US dollars; the FBF codebase canonicalizes monetary values as
`Money(amount, Currency.EUR)`. All monetary values are proportional — the
mathematical result is identical regardless of currency label. No
dollar-to-euro conversion is performed.

### Contribution Semantics

The $5,000/month contribution is **constant in real terms**. No inflation
deflation is applied. The contribution is `Money(Decimal("5000"),
Currency.EUR)` each accumulation month, consistent with the dataset's
real-return convention. This matches the ERN methodology where all values
are in real (inflation-adjusted) units.

### Contribution Ordering (S0-F3)

For each accumulation month:

```
1. Value portfolio at current snapshot prices
2. Add contribution (split by target allocation weights)
3. Rebalance to target allocation weights
4. Apply market return (current snapshot → next snapshot evolution)
```

### Accumulation-to-Retirement Handoff

The accumulation phase produces a final portfolio at dataset[12] prices. This
portfolio becomes the `initial_portfolio` for the retirement simulation.

**Wealth naming convention:**
- `original_initial_wealth`: study-level initial wealth ($2M for Part 42)
- `retirement_initial_wealth`: accumulation-phase output (post-OMY value)
- The `initial_wealth` field in `SimulationContext` refers to
  `retirement_initial_wealth` for the retirement phase.

### Final-Value Target

The Part 42 FV target is 25% of `original_initial_wealth`, not 25% of
`retirement_initial_wealth`. The success criterion is:
`final_wealth >= 0.25 × original_initial_wealth`.

### Accumulation Uniqueness

The accumulation result depends only on `(cohort_start_date,
contribution_amount, allocation_policy, initial_portfolio, dataset)`. It does
not depend on retirement SWR, FV target, or retirement horizon. Therefore
accumulation is computed once per unique cohort, not per retirement parameter
configuration.

**Why:** Avoids redundant computation. For N cohorts × M SWR rates: N
accumulation executions, N×M retirement executions.

**Alternatives rejected:** Computing accumulation per retirement configuration
— rejected because the result is identical and the redundant computation
wastes time without changing the answer.

**Consequence:** The study-plan builder must cache accumulation results by
cohort identity and reuse them across retirement parameter configurations.

### Performance Architecture

The architectural performance model for Part 42:

```
N cohorts × M retirement configurations
          ↓
N accumulation executions + N×M retirement executions
```

No absolute runtime gates are imposed on individual accumulation computations.
The full-study gate is: total Part 42 execution time ≤ 2× the measured
retirement-only baseline on the same machine, output mode, and execution
configuration.
