# AGENTS.md — fbf-core Agent Guide

This is the standalone `fbf-core` repository: simulation engine, research
library, and ERN oracle. See [`README.md`](README.md) for project overview and
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for workflows.

---

## Repository Identity

| Property | Value |
|----------|-------|
| Package name | `fbf-core` |
| Root namespace | `fbf.core` |
| Third-party runtime dependencies | **Zero** |
| Python requirement | ≥ 3.13 |

---

## Absolute Rules

1. **Never import from any CLI package.**
2. **Never add a third-party runtime dependency** to `[project] dependencies`
   in `pyproject.toml`. Dev dependencies are exempt.
3. **Monetary values use `decimal.Decimal`.** Never use `float` for `Money`
   objects or monetary domain operations. Derived statistical metrics may use
   other numeric representations where explicitly appropriate.
4. **The domain layer must remain pure.** `fbf.core.domain` must never import
   from `fbf.core.execution`, `fbf.core.study`, `fbf.core.optimization`,
   `fbf.core.persistence`, or any CLI package.
5. **`fbf.core.execution` must never import `fbf.core.optimization`.**
6. **No legacy imports** (`engine.*`, `research.*`, `infrastructure.*`, old
   `cli.*`) may appear in any production source file.
7. **Do not add `argparse`, `sys.argv`, or presentation logic to Core.**
8. **Do not modify `tests/functional/ern/` constants** without updating the
   canonical ERN acceptance matrix and obtaining explicit user approval.
9. **Datasets are external to the wheel.** Never embed datasets or hardcode
   dataset paths; discovery is explicit via `data_dir` (see `DATASETS.md`).
10. **No machine-specific absolute paths** (`/tmp/`, `/home/`, `/Users/`,
    `C:\`) in `src/` or `tests/`; tests use `tmp_path`.
11. **External CLI-binary use is confined to `tests/functional/`.** The
    black-box ERN harness is the only test surface allowed to drive the
    installed `sim-retire` binary.

---

## Public API Tiers

| Tier | Modules | Who may import |
|------|---------|----------------|
| Tier 1 | `fbf.core` (root `__init__`) | All consumers |
| Tier 2 | `fbf.core.domain`, `fbf.core.domain.model`, `fbf.core.domain.policies`, `fbf.core.study`, `fbf.core.execution`, `fbf.core.optimization`, `fbf.core.persistence`, `fbf.core.research` | CLI and Core |
| Tier 3 | All other submodules | Core tests only — never consumer production code. Consumer tests may use an explicitly documented allow-list. |

---

## Quality Gate

Run from a clean checkout before committing:

```bash
ruff check .
mypy --strict .
pytest -p no:cacheprovider
pytest tests/contract/
```

The full suite skips heavyweight E2E by default. Routine validation must not
set `RUN_ERN_E2E`.

### Heavyweight ERN Workloads

Canonical E2E and research-validation suites live in `tests/functional/ern/`
and are controlled by `RUN_ERN_E2E=1`. They are manual verification tools, not
part of routine validation. Do not run them with E2E variables during ordinary
changes. Commands are in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md#5-functional-validation).

---

## Commit Governance

A phase is complete only after its final commit exists. Implementation and
validation do not imply permission to commit.

Required workflow:

1. Implement the approved scope.
2. Run all required validation.
3. Review the final diff and confirm only approved scope is included.
4. Stop and request explicit user authorization.
5. After authorization, create **exactly one** commit for the phase.
6. Verify the commit hash and clean working tree.

Never commit, amend, rebase, force-push, or rewrite history without explicit
authorization. Do not call generic instructions such as "finish" or "continue"
commit authorization.

---

## Adding a New Public Symbol

1. Implement in the appropriate subpackage.
2. Export from the subpackage `__init__.py`.
3. If Tier 1, add it to `src/fbf/core/__init__.py` and `__all__`.
4. Update `test_public_facade_symbols` in
   `tests/contract/test_core_boundaries.py`.
5. Run `mypy --strict .` and `ruff check .`.

## Adding a New Test

* Unit: `tests/unit/<layer>/test_<module>.py`
* Integration: `tests/integration/`
* Functional: `tests/functional/` (public application/CLI boundary; canonical
  ERN scenarios in `tests/functional/ern/`)
* Contract: `tests/contract/`
* Benchmarks: `tests/benchmarks/`

---

## Breaking API Changes

Breaking changes to Tier 1 or Tier 2 API require a Core minor version increment
and corresponding consumer dependency-pin updates.

---

## Documentation

| Question | Authority |
|---|---|
| Current behaviour | Code + tests |
| Intended architecture | `ARCHITECTURE.md` |
| Design rationale | `docs/DESIGN.md` |
| Rejected alternatives | `docs/DECISIONS.md` |
| ERN methodology and anchors | `docs/ERN_METHODOLOGY.md` |
| Dataset sources and provenance | `DATASETS.md` |
| Development and regeneration | `docs/DEVELOPMENT.md` |
| Unresolved technical work | `TODO.md` |

Documentation describes durable knowledge only. Do not add implementation
reports, session notes, progress snapshots, investigation diaries, completed
roadmaps, or duplicate copies of existing knowledge. Link to the authoritative
source instead.

---

## Engineering Rules

### Repository state

Inspect the actual repository before changing it. Do not rely on conversation
history in place of files, tests, Git state, or configuration.

### Specification divergence

If implementation conflicts with documented intent, stop and identify the
discrepancy. Do not silently redefine intended behaviour.

### Corrections

A correction that closes a specification/behaviour gap requires explicit
approval. After approval, reconcile the specification editorially; do not
rewrite history to erase the divergence.

### YAGNI

Do not add abstractions, extension points, hooks, strategies, callbacks, or
generic interfaces for hypothetical future consumers. A current requirement or
approved architectural need must justify them.

### Validation

Validate changes against the resulting repository state. Run the relevant tests
and quality gates before committing.

### Technical TODOs

`TODO.md` is the canonical register of unresolved technical work. Add an item
only when it is verified, genuinely unfinished, durable beyond the current
session, and specific enough for another contributor to act on.

Do not add session notes, troubleshooting history, environment incidents,
resolved issues, speculative improvements, or competing TODO lists. Remove
items once resolved.
