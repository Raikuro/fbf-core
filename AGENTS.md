# AGENTS.md — fbf-core Agent Guide

This is the standalone `fbf-core` repository.
It contains the simulation engine, research library, and ERN oracle.

---

## Repository Identity

| Property | Value |
|----------|-------|
| Package name | `fbf-core` |
| Root namespace | `fbf.core` |
| Third-party runtime deps | **Zero** |
| Python requirement | ≥ 3.13 |

---

## Absolute Rules

1. **Never import from any CLI package.**
2. **Never add a third-party runtime dependency** to `[project] dependencies` in `pyproject.toml`.
   Dev dependencies (`[project.optional-dependencies] dev`) are exempt.
3. **Monetary values use `decimal.Decimal`.** Never use `float` for `Money` objects or
   monetary domain operations. Derived statistical metrics may use other numeric
   representations where explicitly appropriate.
4. **The domain layer must remain pure.** `fbf.core.domain` must never import from
   `fbf.core.execution`, `fbf.core.study`, `fbf.core.optimization`, `fbf.core.persistence`,
   or any CLI package.
5. **`fbf.core.execution` must never import `fbf.core.optimization`.**
6. **No legacy imports** (`engine.*`, `research.*`, `infrastructure.*`, old `cli.*`) may appear
   in any production source file.
7. **Do not add `argparse`, `sys.argv`, or any presentation logic to Core.**
8. **Do not modify `tests/oracle/ern/`** constants without a corresponding update to
   the canonical ERN acceptance matrix and explicit user approval.
9. **Datasets are external to the wheel.** Never embed datasets in the package or
   hardcode dataset paths; discovery is explicit via `data_dir` (see `DATASETS.md`).
10. **No machine-specific absolute paths** (`/tmp/`, `/home/`, `/Users/`, `C:\`) in
    `src/` or `tests/` — tests use `tmp_path` (enforced by `tests/contract/`).
11. **External CLI-binary use is confined to `tests/oracle/`** — the black-box ERN
    harness is the only test surface allowed to drive the installed `sim-retire` binary
    (enforced by `tests/contract/test_core_boundaries.py`).

---

## Public API Tiers

| Tier | Modules | Who may import |
|------|---------|----------------|
| Tier 1 | `fbf.core` (root `__init__`) | All consumers |
| Tier 2 | `fbf.core.domain`, `fbf.core.domain.model`, `fbf.core.domain.policies`, `fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence` | CLI and Core |
| Tier 3 | All other submodules | Core tests only — never consumer production code. Consumer **tests** may use a small, explicitly documented allow-list (see each consumer's `tests/contract/` directory). |

---

## Quality Gate

Run every command below from a clean checkout **before** committing to `fbf-core`.
A change that does not pass every step is not committed.

```bash
# 1. Lint — must report "All checks passed!"
ruff check src tests

# 2. Type check — must report "Success: no issues found in N source files"
mypy --strict .

# 3. Full test suite (excluding heavyweight E2E) — must be 0 failed
#    The ern_e2e marker tests are skipped by default (RUN_ERN_E2E unset).
#    Routine agent validation MUST NOT enable RUN_ERN_E2E.
pytest -p no:cacheprovider

# 4. Boundary contract — repository independence + tier discipline
pytest tests/contract/
```

`ruff` runs with `--fix` for auto-applicable findings, but the final state must
be clean under the plain `ruff check src tests` form above.

### Heavyweight E2E / Oracle Tests

The ERN SWR replication tests in `tests/oracle/ern/` are heavyweight workloads
(313,020 simulation units across 180 grid cells). They are **not part of the
routine quality gate** and must never be enabled automatically.

**Invocation hierarchy (opt-in via environment variables):**

| Scope | Env vars | Grid | Approx. units |
|-------|----------|------|---------------|
| Routine validation | *(none)* | E2E skipped | 0 |
| Smoke E2E | `RUN_ERN_E2E=1` | 2×2×2 = 8 cells | 13,912 |
| Full grid | `RUN_ERN_E2E=1` + `RUN_ERN_E2E_FULL=1` | 5×9×4 = 180 cells | 313,020 |
| Fast-path full grid | `RUN_ERN_E2E=1` + `RUN_ERN_E2E_FULL=1` + `ERN_E2E_FAST_PATH=1` | 180 cells × 2 paths | 626,040 |

**Manual invocation (developer workstation or CI only):**

```bash
# Smoke grid (quick sanity check):
RUN_ERN_E2E=1 pytest tests/oracle/ -v

# Full 180-cell acceptance grid:
RUN_ERN_E2E=1 RUN_ERN_E2E_FULL=1 pytest tests/oracle/ -v

# Full grid with fast-path equivalence:
RUN_ERN_E2E=1 RUN_ERN_E2E_FULL=1 ERN_E2E_FAST_PATH=1 pytest tests/oracle/ -v
```

Worker count is controlled by `ERN_E2E_WORKERS` (default: `min(8, cpu_count)`).
Set `ERN_E2E_WORKERS=max` for all available logical CPUs.

**Agents must not run `pytest tests/oracle/` with E2E env vars enabled as part
of routine changes.** The oracle tests are a deliberate manual verification tool,
not an automatic gate.

---

## Commit Governance

### Phase completion vs. commit authorization

A phase is **not complete until its final commit has been created successfully**.

However, completing the implementation work does **not** give the agent implicit
permission to create that commit.

The required workflow is:

1. Implement the approved scope.
2. Run all required validation and quality gates.
3. Review the final diff and confirm that only the approved phase scope is included.
4. Prepare the repository for the final phase commit.
5. **Stop and request explicit user authorization to create the commit.**
6. Do not run `git commit` before that authorization is given.
7. After explicit authorization, create **exactly one commit for the phase**.
8. Verify the commit hash and that the working tree is clean.
9. Only then report the phase as `COMPLETE`.

The states must remain distinct:

* **Implementation complete** — all planned changes are implemented.
* **Validation complete** — all required quality gates pass.
* **Ready for commit** — final diff reviewed and approved in scope.
* **Phase complete** — final commit successfully created.

Before authorization, report:

> `PHASE X READY FOR COMMIT — AWAITING AUTHORIZATION`

Do **not** report:

> `PHASE X COMPLETE`

until the commit actually exists.

### One-commit-per-phase rule

Each phase is an atomic delivery unit and must produce **exactly one final commit**.

Do not create intermediate commits for individual tasks, fixes, tests,
documentation changes, or sub-phases unless explicitly authorized otherwise.

If corrections are required before the final commit:

* modify the working tree;
* rerun the relevant validation;
* do not create an intermediate/corrective commit.

### Explicit commit authorization

Immediately before creating the final phase commit, explicitly ask the user
for authorization.

The request must state:

* which phase is being committed;
* the exact scope/files included;
* validation results;
* that the working tree is ready;
* that exactly one commit will be created.

For example:

> Phase X implementation and validation are complete. The final diff contains
> only the approved Phase X scope, all quality gates pass, and the working
> tree is ready. May I create the single final Phase X commit?

Do not interpret generic instructions such as "finish Phase X", "close Phase X",
or "continue" as implicit permission to commit.

Only an explicit authorization to create the commit permits `git commit`.

After authorization, create the single commit, verify its hash and clean
working tree, and only then declare the phase complete.

This policy applies to all future phases unless explicitly overridden by the user.

---

## Adding a New Public Symbol

1. Implement in the appropriate subpackage (`domain/`, `execution/`, etc.).
2. Export from the subpackage's `__init__.py`.
3. If the symbol is Tier 1, add it to `src/fbf/core/__init__.py` and `__all__`.
4. Update `test_public_facade_symbols` in `tests/contract/test_core_boundaries.py`.
5. Run `mypy --strict .` and `ruff check src tests` before committing.

---

## Adding a New Core Test

* Unit tests: `tests/unit/<layer>/test_<module>.py`
* Integration tests: `tests/integration/`
* Benchmark tests: `tests/benchmarks/`
* Oracle tests: `tests/oracle/ern/` (canonical only — do not add ad-hoc oracle tests)
* Boundary contract tests: `tests/contract/`

---

## Breaking API Changes (During 0.x)

Breaking changes to the Tier 1 or Tier 2 public API require a **Core minor version increment**
(e.g. `0.1.x` → `0.2.0`) and must update all consumer dependency pins accordingly.

---

## Documentation

### Authority

| Question                              | Authority                    |
|---------------------------------------|------------------------------|
| What does the code currently do?      | Code + tests                 |
| What is the intended architecture?    | ARCHITECTURE.md              |
| Why does the architecture work this way? | docs/DESIGN.md           |
| Why was a significant alternative rejected? | docs/DECISIONS.md    |
| What technical work remains?          | TODO.md                      |
| How is the repository used?           | README.md                    |
| How should contributors modify it?    | AGENTS.md                    |

### Lifecycle

* **Durable** — changes only when architecture or enduring guidance changes:
  ARCHITECTURE.md, DATASETS.md, docs/DESIGN.md, docs/DECISIONS.md.
* **Operational** — changes as the active project changes: TODO.md, README.md.
* **Behavioral** — changes when engineering rules change: AGENTS.md.
* **Temporary** — should generally not exist in the repository: implementation
  reports, task handoffs, session notes, progress snapshots, benchmark dumps,
  investigation logs.

### Principles

* Documentation describes durable knowledge: architectural intent, boundaries,
  invariants, rationale, constraints, rejected alternatives.
* Code and tests are authoritative for implemented behaviour.
* Do not maintain volatile facts (test counts, commit counts, current branch,
  benchmark numbers). Prefer durable statements.
* Do not copy knowledge across files. Link to the canonical source.
* The project is tool-agnostic. Do not reference specific AI products, agents,
  models, or historical AI workflows.

---

## Engineering Rules

### Repository state

* Inspect the actual repository state before making changes.
* Do not rely on conversational context as a substitute for inspecting files,
  tests, Git state, or configuration.
* Respect repository boundaries.

### Specification divergence

If implementation reveals behaviour or an API that conflicts with the stated
specification or architectural documentation, **stop and identify the
discrepancy**. Do not silently redefine the intended behaviour.

### Corrections and retroactive approval

When a bug fix or implementation correction closes a gap between specification
and behaviour, classify it as a **necessary correction** rather than a contract
change. Corrections require explicit approval but do not require reverting
history. Rewriting the record to erase the divergence destroys the audit trail.

After approval, reconcile the specification document editorially to match the
corrected behaviour. The specification change is editorial, not semantic — it
aligns the document with the intended invariant, not a new one.

### YAGNI

Do not introduce abstractions, extension points, hooks, strategies, callbacks,
or generic interfaces solely for hypothetical future consumers. A current
requirement or explicitly approved architectural need must justify them.

### Validation

Changes must be validated against the resulting repository state. Run the
appropriate tests and quality gates for the affected area before committing.

### Documentation discipline

Documentation should describe durable knowledge. Do not create task reports,
session notes, progress snapshots, or duplicate documentation merely to record
that work was performed. If temporary implementation knowledge has continuing
value, extract it into the appropriate canonical document; otherwise delete it
when the task is complete.

### Reference over duplicate

Do not copy knowledge across files. Link to the canonical source instead. If
code and documentation disagree, correct the code or propose a documentation
update.

### No residual knowledge

Temporary insights gained during implementation must be migrated to permanent
documentation before completion. No knowledge should exist only in a
transient context.

### Technical TODOs

`TODO.md` is the canonical register of unresolved technical work in this
repository. Only add an item when **all** of the following are true:

- the issue is reproducible or otherwise verified;
- it represents genuinely unfinished technical work;
- it has continuing value beyond the current task or session;
- it cannot be considered merely an implementation detail or temporary
  workaround;
- the item is specific enough that another contributor can understand what
  needs to be resolved.

Do **not** add:

- session notes, troubleshooting history, or agent reasoning;
- failed commands, temporary environment problems, or installation retries;
- already-resolved problems;
- speculative future improvements or generic "nice to have" ideas;
- observations that have no actionable consequence.

**Distinguish "discovered issue" from "implementation incident."** A failed
command or workaround during a task is not, by itself, evidence of a
repository defect. Investigate the apparent problem before recording it.
If the issue is a genuine unresolved defect, record it in `TODO.md` in
concise, tool-agnostic terms. Do not copy the investigation narrative.

Remove items once resolved. Remove obsolete or superseded items. Do not
create additional TODO lists, task journals, session notes, or competing
roadmaps.
